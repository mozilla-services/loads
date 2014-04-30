import threading
from Queue import Queue
import errno
import contextlib
import functools

import zmq

from loads.util import json
from loads.transport.exc import TimeoutError, ExecutionError
from loads.transport.message import Message
from loads.util import logger, pack_include_files
from loads.transport.util import (send, recv, DEFAULT_FRONTEND,
                                  timed, DEFAULT_TIMEOUT,
                                  DEFAULT_TIMEOUT_MOVF,
                                  DEFAULT_TIMEOUT_OVF)


class Client(object):
    """Class to drive a Loads cluster.

    Options:

    - **frontend**: ZMQ socket to call.
    - **timeout**: maximum allowed time for a job to run.
      Defaults to 1s.
    - **timeout_max_overflow**: maximum timeout overflow allowed.
      Defaults to 1.5s
    - **timeout_overflows**: number of times in a row the timeout value
      can be overflowed per agent. The client keeps a counter of
      executions that were longer than the regular timeout but shorter
      than **timeout_max_overflow**. When the number goes over
      **timeout_overflows**, the usual TimeoutError is raised.
      When a agent returns on time, the counter is reset.
    - **ssh** ssh tunnel server.
    """
    def __init__(self, frontend=DEFAULT_FRONTEND, timeout=DEFAULT_TIMEOUT,
                 timeout_max_overflow=DEFAULT_TIMEOUT_MOVF,
                 timeout_overflows=DEFAULT_TIMEOUT_OVF,
                 debug=False, ctx=None, ssh=None):
        self.ssh = ssh
        self.kill_ctx = ctx is None
        self.ctx = ctx or zmq.Context()
        self.frontend = frontend
        self.master = self.ctx.socket(zmq.REQ)
        if ssh:
            from zmq import ssh
            ssh.tunnel_connection(self.master, frontend, self.ssh)
        else:
            self.master.connect(frontend)

        self.poller = zmq.Poller()
        self.poller.register(self.master, zmq.POLLIN)
        self.timeout = timeout * 1000
        self.lock = threading.Lock()
        self.timeout_max_overflow = timeout_max_overflow * 1000
        self.timeout_overflows = timeout_overflows
        self.debug = debug

    def execute(self, job, timeout=None, log_exceptions=True):
        """Runs the job

        Options:

        - **job**: Job to be performed. Can be a :class:`Job`
          instance or a string. If it's a string a :class:`Job` instance
          will be automatically created out of it.
        - **timeout**: maximum allowed time for a job to run.
          If not provided, uses the one defined in the constructor.

        If the job fails after the timeout, raises a :class:`TimeoutError`.

        This method is thread-safe and uses a lock. If you need to execute a
        lot of jobs simultaneously on a broker, use the :class:`Pool` class.

        """
        if timeout is None:
            timeout = self.timeout_max_overflow

        try:
            duration, res = timed(self.debug)(self._execute)(job, timeout)
        except Exception:
            # logged, connector replaced.
            if log_exceptions:
                logger.exception('Failed to execute the job.')
            logger.debug(str(job))
            raise

        if 'error' in res:
            raise ValueError(res['error'])

        return res['result']

    def close(self):
        self.master.setsockopt(zmq.LINGER, 0)
        self.master.close()

        if self.kill_ctx:
            self.ctx.destroy(0)

    def _execute(self, job, timeout=None):

        if not isinstance(job, Message):
            job = Message(**job)

        if timeout is None:
            timeout = self.timeout_max_overflow

        with self.lock:
            send(self.master, job.serialize())

            while True:
                try:
                    socks = dict(self.poller.poll(timeout))
                    break
                except zmq.ZMQError as e:
                    if e.errno != errno.EINTR:
                        raise

        if socks.get(self.master) == zmq.POLLIN:
            data = recv(self.master)
            return json.loads(data)

        raise TimeoutError(timeout)

    def run(self, args, async=True):
        # let's ask the broker how many agents it has
        res = self.execute({'command': 'LIST'})

        # do we have enough ?
        agents = len(res)
        agents_needed = args.get('agents', 1)
        if len(res) < agents_needed:
            msg = 'Not enough agents running on that broker. '
            msg += 'Asked: %d, Got: %d' % (agents_needed, agents)

            raise ExecutionError(msg)

        # let's copy over some files if we need
        includes = args.get('include_file', [])

        cmd = {'command': 'CTRL_RUN',
               'async': async,
               'agents': agents_needed,
               'args': args}

        cmd['filedata'] = pack_include_files(includes)
        res = self.execute(cmd)
        logger.debug('Run on its way')
        logger.debug(res)
        return res

    def ping(self, timeout=None, log_exceptions=True):
        return self.execute({'command': 'PING'}, timeout=timeout,
                            log_exceptions=log_exceptions)

    def list(self):
        return self.execute({'command': 'LIST'})

    #
    # commands handled by the broker controller.
    #
    def list_runs(self):
        return self.execute({'command': 'CTRL_LIST_RUNS'})

    def get_urls(self, run_id):
        return self.execute({'command': 'CTRL_GET_URLS', 'run_id': run_id})

    def stop_run(self, run_id):
        return self.execute({'command': 'CTRL_STOP_RUN', 'run_id': run_id})

    def get_counts(self, run_id):
        res = self.execute({'command': 'CTRL_GET_COUNTS', 'run_id': run_id})
        # XXX why ?
        if isinstance(res, dict):
            return res.items()
        return res

    def get_metadata(self, run_id):
        return self.execute({'command': 'CTRL_GET_METADATA', 'run_id': run_id})

    def get_data(self, run_id, **kw):
        cmd = {'command': 'CTRL_GET_DATA', 'run_id': run_id}
        cmd.update(kw)
        return self.execute(cmd)

    def status(self, agent_id):
        return self.execute({'command': 'CTRL_AGENT_STATUS',
                             'agent_id': agent_id})

    def stop(self, agent_id):
        return self.execute({'command': 'CTRL_AGENT_STOP',
                             'agent_id': agent_id})

    def purge_broker(self):
        runs = self.list_runs()
        if len(runs) == 0:
            return runs
        for run_id, workers in runs.items():
            self.stop_run(run_id)
        return runs


class Pool(object):
    """The pool class manage several :class:`Client` instances
    and publish the same interface,

    Options:

    - **size**: size of the pool. Defaults to 10.
    - **frontend**: ZMQ socket to call.
    - **timeout**: maximum allowed time for a job to run.
      Defaults to 5s.
    - **timeout_max_overflow**: maximum timeout overflow allowed
    - **timeout_overflows**: number of times in a row the timeout value
      can be overflowed per agent. The client keeps a counter of
      executions that were longer than the regular timeout but shorter
      than **timeout_max_overflow**. When the number goes over
      **timeout_overflows**, the usual TimeoutError is raised.
      When a agent returns on time, the counter is reset.
    """
    def __init__(self, size=10, frontend=DEFAULT_FRONTEND,
                 timeout=DEFAULT_TIMEOUT,
                 timeout_max_overflow=DEFAULT_TIMEOUT_MOVF,
                 timeout_overflows=DEFAULT_TIMEOUT_OVF,
                 debug=False, ctx=None):
        self._connectors = Queue()
        self.frontend = frontend
        self.timeout = timeout
        self.timeout_overflows = timeout_overflows
        self.timeout_max_overflow = timeout_max_overflow
        self.debug = debug
        self.ctx = ctx or zmq.Context()

        for i in range(size):
            self._connectors.put(self._create_client())

    def _create_client(self):
        return Client(self.frontend, self.timeout,
                      self.timeout_max_overflow, self.timeout_overflows,
                      debug=self.debug, ctx=self.ctx)

    @contextlib.contextmanager
    def _connector(self, timeout):
        connector = self._connectors.get(timeout=timeout)
        try:
            yield connector
        except Exception:
            # connector replaced
            try:
                connector.close()
            finally:
                self._connectors.put(self._create_client())
            raise
        else:
            self._connectors.put(connector)

    def __getattribute__(self, name):
        if not hasattr(Client, name):
            return object.__getattribute__(self, name)
        return functools.partial(self._runner, name)

    def _runner(self, name, *args, **kw):
        timeout = kw.get('timeout', self.timeout)
        with self._connector(timeout) as connector:
            meth = getattr(connector, name)
            return meth(*args, **kw)

    def close(self):
        self.ctx.destroy(0)

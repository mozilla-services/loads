import threading
from Queue import Queue
import errno
import contextlib
import json
import zlib
import os

import zmq

from loads.transport.exc import TimeoutError, ExecutionError
from loads.transport.message import Message
from loads.util import logger, glob
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
      can be overflowed per worker. The client keeps a counter of
      executions that were longer than the regular timeout but shorter
      than **timeout_max_overflow**. When the number goes over
      **timeout_overflows**, the usual TimeoutError is raised.
      When a worker returns on time, the counter is reset.
    """
    def __init__(self, frontend=DEFAULT_FRONTEND, timeout=DEFAULT_TIMEOUT,
                 timeout_max_overflow=DEFAULT_TIMEOUT_MOVF,
                 timeout_overflows=DEFAULT_TIMEOUT_OVF,
                 debug=False, ctx=None):
        self.kill_ctx = ctx is None
        self.ctx = ctx or zmq.Context()
        self.frontend = frontend
        self.master = self.ctx.socket(zmq.REQ)
        self.master.connect(frontend)
        logger.debug('Client connected to %s' % frontend)
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
            raise

        if 'error' in res:
            raise ValueError(res['error'])
        return res['result']

    def close(self):
        #self.master.close()
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
            return json.loads(recv(self.master))

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

        cmd = {'command': 'RUN',
               'async': async,
               'agents': agents_needed,
               'args': args}

        files = {}

        for file_ in glob(includes):
            logger.debug('Compressing %r' % file_)

            # no stream XXX
            if os.path.isdir(file_):
                for root, dirs, _files in os.walk(file_):
                    for f in _files:
                        fullname = os.path.join(root, f)
                        with open(fullname) as f:
                            data = zlib.compress(f.read()).decode('latin1')
                        files[fullname] = data
            else:
                with open(file_) as f:
                    data = zlib.compress(f.read()).decode('latin1')

                files[file_] = data

        cmd['files'] = files
        res = self.execute(cmd)
        logger.debug('Run on its way')
        logger.debug(res)
        return res

    def ping(self, timeout=None, log_exceptions=True):
        return self.execute({'command': 'PING'}, timeout=timeout,
                            log_exceptions=log_exceptions)

    def get_data(self, run_id):
        return self.execute({'command': 'GET_DATA', 'run_id': run_id})

    def get_counts(self, run_id):
        res = self.execute({'command': 'GET_COUNTS', 'run_id': run_id})
        # XXX why ?
        if isinstance(res, dict):
            return res.items()
        return res

    def get_metadata(self, run_id):
        return self.execute({'command': 'GET_METADATA', 'run_id': run_id})

    def status(self, worker_id):
        return self.execute({'command': 'STATUS', 'worker_id': worker_id})

    def stop(self, worker_id):
        return self.execute({'command': 'STOP', 'worker_id': worker_id})

    def stop_run(self, run_id):
        return self.execute({'command': 'STOPRUN', 'run_id': run_id})

    def list(self):
        return self.execute({'command': 'LIST'})

    def list_runs(self):
        return self.execute({'command': 'LISTRUNS'})


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
      can be overflowed per worker. The client keeps a counter of
      executions that were longer than the regular timeout but shorter
      than **timeout_max_overflow**. When the number goes over
      **timeout_overflows**, the usual TimeoutError is raised.
      When a worker returns on time, the counter is reset.
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

    def execute(self, job, timeout=None):
        with self._connector(timeout) as connector:
            return connector.execute(job, timeout)

    def close(self):
        self.ctx.destroy(0)

    def ping(self, timeout=None):
        with self._connector(self.timeout) as connector:
            return connector.ping(timeout)

    def run(self, args, async=True):
        with self._connector(self.timeout) as connector:
            return connector.run(args, async)

    def status(self, worker_id):
        with self._connector(self.timeout) as connector:
            return connector.status(worker_id)

    def list(self):
        with self._connector(self.timeout) as connector:
            return connector.list()

    def list_runs(self):
        with self._connector(self.timeout) as connector:
            return connector.list_runs()

    def stop(self, worker_id):
        with self._connector(self.timeout) as connector:
            return connector.stop(worker_id)

    def get_data(self, run_id):
        with self._connector(self.timeout) as connector:
            return connector.get_data(run_id)

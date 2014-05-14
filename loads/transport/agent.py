""" The agent does several things:

- maintains a connection to a master
- gets load testing orders & performs them
- sends back the results in real time.
"""
import tempfile
import argparse
import errno
import logging
import os
import random
import subprocess
import shlex
import sys
import time
import traceback
from collections import defaultdict
import functools

import zmq
from zmq.eventloop import ioloop, zmqstream

from loads.transport import util
from loads.util import logger, set_logger, json, unpack_include_files
from loads.transport.util import (DEFAULT_FRONTEND, DEFAULT_TIMEOUT_MOVF,
                                  DEFAULT_MAX_AGE, DEFAULT_MAX_AGE_DELTA,
                                  get_hostname)
from loads.transport.message import Message
from loads.transport.util import decode_params, timed
from loads.transport.heartbeat import Stethoscope
from loads.transport.client import Client


class ExecutionError(Exception):
    pass


class Agent(object):
    """Class that links a callable to a broker.

    Options:

    - **broker**: The ZMQ socket to connect to the broker.
    - **ping_delay**: the delay in seconds betweem two pings.
    - **ping_retries**: the number of attempts to ping the broker before
      quitting.
    - **params** a dict containing the params to set for this agent.
    - **timeout** the maximum time allowed before the thread stacks is dump
      and the message result not sent back.
    - **max_age**: maximum age for a agent in seconds. After that delay,
      the agent will simply quit. When set to -1, never quits.
      Defaults to -1.
    - **max_age_delta**: maximum value in seconds added to max age.
      The agent will quit after *max_age + random(0, max_age_delta)*
      This is done to avoid having all agents quit at the same instant.
      Defaults to 0. The value must be an integer.
    """
    def __init__(self, broker=DEFAULT_FRONTEND,
                 ping_delay=10., ping_retries=3,
                 params=None, timeout=DEFAULT_TIMEOUT_MOVF,
                 max_age=DEFAULT_MAX_AGE, max_age_delta=DEFAULT_MAX_AGE_DELTA):
        logger.debug('Initializing the agent.')
        self.debug = logger.isEnabledFor(logging.DEBUG)
        self.params = params
        self.pid = os.getpid()
        self.agent_id = '%s-%s' % (get_hostname(), self.pid)
        self.timeout = timeout
        self.max_age = max_age
        self.max_age_delta = max_age_delta
        self.env = os.environ.copy()
        self.running = False
        self._workers = {}
        self._max_id = defaultdict(int)

        # Let's ask the broker its options
        self.broker = broker
        client = Client(self.broker)

        # this will timeout in case the broker is unreachable
        result = client.ping()
        self.endpoints = result['endpoints']

        # Setup the zmq sockets
        self.loop = ioloop.IOLoop()
        self.ctx = zmq.Context()

        # backend socket - used to receive work from the broker
        self._backend = self.ctx.socket(zmq.ROUTER)
        self._backend.identity = self.agent_id
        self._backend.connect(self.endpoints['backend'])

        # register socket - used to register into the broker
        self._reg = self.ctx.socket(zmq.PUSH)
        self._reg.connect(self.endpoints['register'])

        # hearbeat socket - used to check if the broker is alive
        heartbeat = self.endpoints.get('heartbeat')

        if heartbeat is not None:
            logger.info("Hearbeat activated")
            self.ping = Stethoscope(heartbeat, onbeatlost=self.lost,
                                    delay=ping_delay, retries=ping_retries,
                                    ctx=self.ctx, io_loop=self.loop,
                                    onregister=self.register)
        else:
            self.ping = None

        # Setup the zmq streams.
        self._backstream = zmqstream.ZMQStream(self._backend, self.loop)
        self._backstream.on_recv(self._handle_recv_back)

        self._check = ioloop.PeriodicCallback(self._check_proc,
                                              ping_delay * 1000,
                                              io_loop=self.loop)

    def _run(self, args, run_id=None):
        logger.debug('Starting a run.')

        args['batched'] = True
        args['slave'] = True
        args['agent_id'] = self.agent_id
        args['zmq_receiver'] = self.endpoints['receiver']
        args['run_id'] = run_id

        cmd = 'from loads.main import run;'
        cmd += 'run(%s)' % str(args)
        cmd = sys.executable + ' -c "%s"' % cmd
        cmd = shlex.split(cmd)
        try:
            proc = subprocess.Popen(cmd, cwd=args.get('test_dir'))
        except Exception, e:
            msg = 'Failed to start process ' + str(e)
            logger.debug(msg)
            raise ExecutionError(msg)

        self._workers[proc.pid] = proc, run_id
        self._sync_hb()
        return proc.pid

    def _sync_hb(self):
        if self.ping is None:
            return

        if len(self._workers) > 0 and self.ping.running:
            self.ping.stop()
        elif len(self._workers) == 0 and not self.ping.running:
            self.ping.start()

    def _status(self, command, data):
        status = {}
        run_id = data.get('run_id')

        for pid, (proc, _run_id) in self._workers.items():
            if run_id is not None and run_id != _run_id:
                continue

            if proc.poll() is None:
                status[pid] = {'status': 'running', 'run_id': _run_id}
            else:
                status[pid] = {'status': 'terminated', 'run_id': _run_id}

        res = {'result': {'status': status,
                          'command': command}}

        return res

    def _handle_commands(self, message):
        # we get the messages from the broker here
        data = message.data
        command = data['command']
        logger.debug('Received command %s' % command)

        if command == 'RUN':
            test_dir = data['args'].get('test_dir')
            if test_dir is None:
                test_dir = tempfile.mkdtemp()
            else:
                test_dir += self.agent_id

            if not os.path.exists(test_dir):
                os.makedirs(test_dir)

            data['args']['test_dir'] = test_dir

            # XXX should be done in _run or at least asynchronously
            filedata = data.get('filedata')
            if filedata:
                unpack_include_files(filedata, test_dir)

            args = data['args']
            run_id = data.get('run_id')
            pid = self._run(args, run_id)

            return {'result': {'pids': [pid],
                               'agent_id': self.agent_id,
                               'command': command}}

        elif command in ('STATUS', '_STATUS'):
            return self._status(command, data)

        elif command == 'STOP':
            logger.debug('asked to STOP all runs')
            return self._stop_runs(command)

        elif command == 'QUIT':
            if len(self._workers) > 0 and not data.get('force', False):
                # if we're busy we won't quit - unless forced !
                logger.info("Broker asked us to quit ! But we're busy...")
                logger.info("Cowardly refusing to die")
                return self._status(command, data)

            logger.debug('asked to QUIT')
            try:
                return self._stop_runs(command)
            finally:
                os._exit(0)

        raise NotImplementedError(command)

    def _kill_worker(self, proc):
        pid = proc.pid
        logger.debug('%d final termination' % proc.pid)

        if proc.poll() is None:
            logger.debug('Calling kill on %d' % proc.pid)
            try:
                proc.kill()
            except OSError:
                logger.exception('Cannot kill %d' % pid)

    def _stop_runs(self, command):
        status = {}
        for pid, (proc, run_id) in self._workers.items():
            logger.debug('terminating proc for run %s' % str(run_id))

            if proc.poll() is None:
                logger.debug('Starting the graceful period for the worker')
                proc.terminate()
                delay = time.time() + 5
                kill = functools.partial(self._kill_worker, proc)
                self.loop.add_timeout(delay, kill)
                if pid in self._workers:
                    del self._workers[pid]

            status[pid] = {'status': 'terminated', 'run_id': run_id}

        self.loop.add_callback(self._sync_hb)
        return {'result': {'status': status,
                           'command': command}}

    def _check_proc(self):
        for pid, (proc, run_id) in self._workers.items():
            if not proc.poll() is None:
                del self._workers[pid]
        self._sync_hb()

    def _handle_recv_back(self, msg):
        # do the message and send the result
        if self.debug:
            target = timed()(self._handle_commands)
        else:
            target = self._handle_commands

        duration = -1
        broker_id = msg[2]

        if len(msg) == 7:
            client_id = msg[4]
        else:
            client_id = None

        data = msg[-1]
        try:
            res = target(Message.load_from_string(data))
            if self.debug:
                duration, res = res

            res['hostname'] = get_hostname()
            res['agent_id'] = self.agent_id
            res['pid'] = self.pid

            res = json.dumps(res)
            # we're working with strings
            if isinstance(res, unicode):
                res = res.encode('utf8')

        except Exception, e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc = traceback.format_tb(exc_traceback)
            exc.insert(0, str(e))
            res = {'error': {'agent_id': self.agent_id,
                             'error': '\n'.join(exc)}}
            logger.error(res)

        data = [broker_id, '', str(self.agent_id), '']

        if client_id is not None:
            data += [client_id, '']

        data.append(res)
        print 'send ' + str(data)
        try:
            self._backend.send_multipart(data)
        except Exception:
            logging.error("Could not send back the result", exc_info=True)

    def lost(self):
        if len(self._workers) > 0:
            # if we're busy we won't quit!
            logger.info("Broker lost ! But we're busy...")
            return False

        logger.info('Broker lost ! Quitting..')
        self.loop.add_callback(self._stop)
        return True

    def stop(self):
        """Stops the agent.
        """
        if not self.running:
            return

        # telling the broker we are stopping
        try:
            self._reg.send_multipart(['UNREGISTER', self.agent_id])
        except zmq.ZMQError:
            logger.debug('Could not unregister')

        # give it a chance to finish a message
        logger.debug('Starting the graceful period')
        delay = time.time() + self.timeout
        self.loop.add_timeout(delay, self._stop)

    def _stop(self):
        logger.debug('Stopping the agent')
        self.running = False
        try:
            self._backstream.flush()
        except zmq.core.error.ZMQError:
            pass

        try:
            self.loop.stop()
            logger.debug('Agent is stopped')
        finally:
            logger.debug('Exiting...')
            os._exit(0)

    def register(self):
        # telling the broker we are ready
        data = {'pid': self.pid, 'hostname': get_hostname(),
                'agent_id': self.agent_id}
        self._reg.send_multipart(['REGISTER', json.dumps(data)])

    def start(self):
        """Starts the agent
        """
        util.PARAMS = self.params
        logger.debug('Starting the agent loop')

        if self.ping is not None:
            # running the pinger
            self.ping.start()
        self._check.start()
        self.running = True

        # telling the broker we are ready
        self.register()

        # arming the exit callback
        if self.max_age != -1:
            if self.max_age_delta > 0:
                delta = random.randint(0, self.max_age_delta)
            else:
                delta = 0

            cb_time = self.max_age + delta
            self.loop.add_timeout(time.time() + cb_time, self.stop)

        while self.running:
            try:
                self.loop.start()
            except zmq.ZMQError as e:
                logger.debug(str(e))

                if e.errno == errno.EINTR:
                    continue
                elif e.errno == zmq.ETERM:
                    break
                else:
                    logger.debug("got an unexpected error %s (%s)", str(e),
                                 e.errno)
                    raise
            else:
                break

        logger.debug('Agent loop over')


def main(args=sys.argv):
    parser = argparse.ArgumentParser(description='Run an agent.')

    parser.add_argument('--broker', dest='broker',
                        default=DEFAULT_FRONTEND,
                        help="ZMQ socket to the broker.")

    parser.add_argument('--debug', action='store_true', default=False,
                        help="Debug mode")

    parser.add_argument('--logfile', dest='logfile', default='stdout',
                        help="File to log in to.")

    parser.add_argument('--params', dest='params', default=None,
                        help='The parameters to be used by the agent.')

    parser.add_argument('--timeout', dest='timeout', type=float,
                        default=DEFAULT_TIMEOUT_MOVF,
                        help=('The maximum time allowed before the thread '
                              'stacks is dump and the message result not sent '
                              'back.'))

    parser.add_argument('--max-age', dest='max_age', type=float,
                        default=DEFAULT_MAX_AGE,
                        help=('The maximum age for a worker in seconds. '
                              'After that delay, the worker will simply quit. '
                              'When set to -1, never quits.'))

    parser.add_argument('--max-age-delta', dest='max_age_delta', type=int,
                        default=DEFAULT_MAX_AGE_DELTA,
                        help='The maximum value in seconds added to max_age')

    args = parser.parse_args()
    set_logger(args.debug, logfile=args.logfile)
    sys.path.insert(0, os.getcwd())  # XXX

    if args.params is None:
        params = {}
    else:
        params = decode_params(args.params)

    logger.info('Connecting to %s' % args.broker)
    agent = Agent(broker=args.broker, params=params,
                  timeout=args.timeout, max_age=args.max_age,
                  max_age_delta=args.max_age_delta)

    try:
        agent.start()
    except KeyboardInterrupt:
        return 1
    finally:
        agent.stop()

    return 0


if __name__ == '__main__':
    main()

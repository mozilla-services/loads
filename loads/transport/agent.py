""" The agent does several things:

- maintains a connection to a master
- gets load testing orders & performs them
- sends back the results in real time.
"""
import argparse
import errno
import json
import logging
import os
import random
import subprocess
import shlex
import sys
import time
import traceback
import zlib

import zmq
from zmq.eventloop import ioloop, zmqstream

from loads.transport import util
from loads.util import logger, set_logger
from loads.transport.util import (DEFAULT_FRONTEND, DEFAULT_TIMEOUT_MOVF,
                                  DEFAULT_MAX_AGE, DEFAULT_MAX_AGE_DELTA,
                                  DEFAULT_AGENT_RECEIVER, register_ipc_file)
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
    - **receiver**: The ZMQ socket which will receive data about the test run.
                    this one should contain a "{pid}" section which will be
                    replaced by the pid of the agent, since each receiving
                    socket between the agent and the workers should be unique.
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
                 receiver=DEFAULT_AGENT_RECEIVER,
                 ping_delay=10., ping_retries=3,
                 params=None, timeout=DEFAULT_TIMEOUT_MOVF,
                 max_age=DEFAULT_MAX_AGE, max_age_delta=DEFAULT_MAX_AGE_DELTA):
        logger.debug('Initializing the agent.')
        self.debug = logger.isEnabledFor(logging.DEBUG)
        self.params = params
        self.pid = os.getpid()
        self.timeout = timeout
        self.max_age = max_age
        self.max_age_delta = max_age_delta
        self.delayed_exit = None
        self.env = os.environ.copy()
        self.running = False
        self._processes = {}
        self._started = self._stopped = self._launched = 0

        self.loop = ioloop.IOLoop()
        self.ctx = zmq.Context()

        # Setup the zmq sockets

        # Let's ask the broker its options
        self.broker = broker
        client = Client(self.broker)
        result = client.ping()
        self.endpoints = result['endpoints']

        # backend socket - used to receive work from the broker
        self._backend = self.ctx.socket(zmq.REP)
        self._backend.identity = str(os.getpid())
        self._backend.connect(self.endpoints['backend'])

        # register socket - used to register into the broker
        self._reg = self.ctx.socket(zmq.PUSH)
        self._reg.connect(self.endpoints['register'])

        # receiver socket - used to receive results from workers
        self._receiver_socket = receiver.format(pid=self.pid)
        register_ipc_file(self._receiver_socket)
        self._receiver = self.ctx.socket(zmq.PULL)
        self._receiver.bind(self._receiver_socket)

        # push socket - used to send back results to the broker
        self._push = self.ctx.socket(zmq.PUSH)
        self._push.set_hwm(8096 * 10)
        self._push.setsockopt(zmq.LINGER, -1)
        self._push.connect(self.endpoints['receiver'])

        # hearbeat socket - used to check if the broker is alive
        heartbeat = self.endpoints.get('heartbeat')

        if heartbeat is not None:
            self.ping = Stethoscope(heartbeat, onbeatlost=self.lost,
                                    delay=ping_delay, retries=ping_retries,
                                    ctx=self.ctx, io_loop=self.loop)
        else:
            self.ping = None

        # Setup the zmq streams.
        self._backstream = zmqstream.ZMQStream(self._backend, self.loop)
        self._backstream.on_recv(self._handle_recv_back)
        self._rcvstream = zmqstream.ZMQStream(self._receiver, self.loop)
        self._rcvstream.on_recv(self._handle_events)

        self._check = ioloop.PeriodicCallback(self._check_proc,
                                              ping_delay * 1000,
                                              io_loop=self.loop)

    def _copy_files(self, data):
        old_dir = os.getcwd()
        try:
            test_dir = data['args'].get('test_dir')

            if test_dir is not None:
                if not os.path.exists(test_dir):
                    logger.debug('Creating the test directory "%r"' % test_dir)
                    os.makedirs(test_dir)

                logger.debug('Moving to %r' % test_dir)
                os.chdir(test_dir)

            for filename, file_data in data['files'].items():
                dirname = os.path.dirname(filename)
                if not os.path.exists(dirname):
                    os.makedirs(dirname)

                with open(filename, 'w') as f:
                    logger.debug('Creating %r in %r' % (filename,
                                                        os.getcwd()))
                    file_data = file_data.encode('latin1')
                    f.write(zlib.decompress(file_data))
        finally:
            os.chdir(old_dir)

    def _run(self, args, run_id=None):
        logger.debug('Starting a run.')
        self._started = self._stopped = 0

        args['slave'] = True
        args['worker_id'] = os.getpid()
        args['zmq_receiver'] = self._receiver_socket

        test_runner = args.get('test_runner', None)
        if test_runner is not None:
            # we have a custom runner
            nb_runs = (args['users'][0] or 1) * (args['hits'][0] or 1)

        try:
            if test_runner is not None:
                self._launched = nb_runs
                procs = self.launch_multiple_runners(nb_runs, args)
            else:
                self._launched = 1
                cmd = 'from loads.main import run;'
                cmd += 'run(%s)' % str(args)
                cmd = sys.executable + ' -c "%s"' % cmd
                cmd = shlex.split(cmd)
                procs = [subprocess.Popen(cmd, cwd=args.get('test_dir'))]

        except Exception, e:
            msg = 'Failed to start process ' + str(e)
            raise ExecutionError(msg)

        pids = []
        for proc in procs:
            self._processes[proc.pid] = proc, run_id
            pids.append(proc.pid)

        return pids

    def launch_multiple_runners(self, nb, args):
        cmd = args['test_runner'].format(test=args['fqn'])

        procs = []
        for x in range(nb):
            loads_status = ','.join(map(str, (args['hits'][0],
                                              args['users'][0],
                                              x + 1, 1)))
            env = os.environ.copy()
            env['LOADS_WORKER_ID'] = str(args.get('worker_id'))
            env['LOADS_STATUS'] = loads_status
            env['LOADS_ZMQ_RECEIVER'] = self._receiver_socket
            cmd_args = {'env': env,
                        'stdout': subprocess.PIPE,
                        'cwd': args.get('test_dir'),
                        }
            procs.append(subprocess.Popen(cmd.split(' '), **cmd_args))

        return procs

    def _handle_commands(self, message):
        # we get the messages from the broker here
        data = message.data
        command = data['command']

        if command == 'RUN':
            logger.debug('Received run.')
            logger.debug(message.data)

            # XXX should be done in _run or at least asynchronously
            if 'files' in data:
                self._copy_files(data)

            args = data['args']
            run_id = data.get('run_id')
            pids = self._run(args, run_id)

            return {'result': {'pids': pids,
                               'worker_id': str(os.getpid()),
                               'command': command}}

        elif command in ('STATUS', '_STATUS'):
            status = {}
            run_id = data.get('run_id')

            for pid, (proc, _run_id) in self._processes.items():
                if run_id is not None and run_id != _run_id:
                    continue

                if proc.poll() is None:
                    status[pid] = 'running'
                else:
                    status[pid] = 'terminated'

            res = {'result': {'status': status,
                              'command': command}}

            logger.debug('Status: %s' % str(res))
            return res
        elif command == 'STOP':
            return self._stop_runs(command)
        elif command == 'QUIT':
            try:
                return self._stop_runs(command)
            finally:
                sys.exit(0)

        raise NotImplementedError()

    def _stop_runs(self, command):
        status = {}
        for pid, (proc, run_id) in self._processes.items():
            if proc.poll() is None:
                proc.terminate()
                del self._processes[pid]
            status[pid] = 'terminated'

        return {'result': {'status': status,
                           'command': command}}

    def _check_proc(self):
        for pid, (proc, run_id) in self._processes.items():
            if not proc.poll() is None:
                del self._processes[pid]

    def _handle_events(self, msg):
        # Here we receive all the events from the runners.
        # Proxy them to the broker unless they are startTestRun / stopTestRun,
        # because we want to be sure all the test runs are actually finished
        # before sending these signals there (as they stop the whole test run)
        data = json.loads(msg[0])
        data_type = data['data_type']

        if data_type == 'startTestRun':
            if self._started == 0:
                self._stopped = 0
                self._push.send(msg[0])
            self._started += 1

        elif data_type == 'stopTestRun':
            self._stopped += 1
            if self._stopped == self._launched:
                self._push.send(msg[0])

                # reinitialize the counters
                self._started = 0
                self._stopped = 0
        else:
            self._push.send(msg[0])

    def _handle_recv_back(self, msg):
        # do the message and send the result
        if self.debug:
            #logger.debug('Message received from the broker')
            target = timed()(self._handle_commands)
        else:
            target = self._handle_commands

        duration = -1

        try:
            res = target(Message.load_from_string(msg[0]))
            if self.debug:
                duration, res = res

            res = json.dumps(res)
            # we're working with strings
            if isinstance(res, unicode):
                res = res.encode('utf8')

        except Exception, e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc = traceback.format_tb(exc_traceback)
            exc.insert(0, str(e))
            res = {'error': {'worker_pid': self.pid, 'error': '\n'.join(exc)}}
            logger.error(res)

        try:
            self._backstream.send(res)
        except Exception:
            logging.error("Could not send back the result", exc_info=True)

    def lost(self):
        logger.info('Broker lost ! Quitting..')
        self.running = False
        self.loop.stop()
        return True

    def stop(self):
        """Stops the agent.
        """
        if not self.running:
            return

        # telling the broker we are stopping
        try:
            self._reg.send_multipart(['UNREGISTER', str(os.getpid())])
        except zmq.ZMQError:
            logger.debug('Could not unregister')

        # give it a chance to finish a message
        logger.debug('Starting the graceful period')
        self.graceful_delay = ioloop.DelayedCallback(self._stop,
                                                     self.timeout * 1000,
                                                     io_loop=self.loop)
        self.graceful_delay.start()

    def _stop(self):
        logger.debug('Stopping the agent')
        self.running = False
        try:
            self._backstream.flush()
        except zmq.core.error.ZMQError:
            pass
        self.loop.stop()
        if self.ping is not None:
            self.ping.stop()
        self._check.stop()
        time.sleep(.1)
        self.ctx.destroy(0)
        logger.debug('Agent is stopped')

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
        self._reg.send_multipart(['REGISTER', str(os.getpid())])

        # arming the exit callback
        if self.max_age != -1:
            if self.max_age_delta > 0:
                delta = random.randint(0, self.max_age_delta)
            else:
                delta = 0

            cb_time = self.max_age + delta
            self.delayed_exit = ioloop.DelayedCallback(self.stop,
                                                       cb_time * 1000,
                                                       io_loop=self.loop)
            self.delayed_exit.start()

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

    parser.add_argument('--receiver', dest='receiver',
                        default=DEFAULT_AGENT_RECEIVER,
                        help="ZMQ socket to get results from workers.")

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
    agent = Agent(broker=args.broker, receiver=args.receiver,
                  params=params, timeout=args.timeout, max_age=args.max_age,
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

""" The agent does several things:

- maintains a connection to a master
- gets load testing orders & performs them
- sends back the results in RT
"""
import os
import errno
import time
import sys
import traceback
import argparse
import logging
import threading
import random
import json
import functools

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from loads.runner import run
from loads.transport import util
from loads.util import logger, set_logger
from loads.transport.util import (DEFAULT_BACKEND,
                                  DEFAULT_HEARTBEAT, DEFAULT_REG,
                                  DEFAULT_TIMEOUT_MOVF, DEFAULT_MAX_AGE,
                                  DEFAULT_MAX_AGE_DELTA)
from loads.transport.message import Message
from loads.transport.util import decode_params, timed
from loads.transport.heartbeat import Stethoscope


__ = json.dumps


class Agent(object):
    """Class that links a callable to a broker.

    Options:

    - **backend**: The ZMQ socket to connect to the broker.
    - **heartbeat**: The ZMQ socket to perform PINGs on the broker to make
      sure it's still alive.
    - **register** : the ZMQ socket to register workers
    - **ping_delay**: the delay in seconds betweem two pings.
    - **ping_retries**: the number of attempts to ping the broker before
      quitting.
    - **params** a dict containing the params to set for this worker.
    - **timeout** the maximum time allowed before the thread stacks is dump
      and the message result not sent back.
    - **max_age**: maximum age for a worker in seconds. After that delay,
      the worker will simply quit. When set to -1, never quits.
      Defaults to -1.
    - **max_age_delta**: maximum value in seconds added to max age.
      The Worker will quit after *max_age + random(0, max_age_delta)*
      This is done to avoid having all workers quit at the same instant.
      Defaults to 0. The value must be an integer.
    """
    def __init__(self, backend=DEFAULT_BACKEND,
                 heartbeat=DEFAULT_HEARTBEAT, register=DEFAULT_REG,
                 ping_delay=10., ping_retries=3,
                 params=None, timeout=DEFAULT_TIMEOUT_MOVF,
                 max_age=DEFAULT_MAX_AGE, max_age_delta=DEFAULT_MAX_AGE_DELTA):
        logger.debug('Initializing the worker.')
        self.ctx = zmq.Context()
        self.backend = backend
        self._reg = self.ctx.socket(zmq.PUSH)
        self._reg.connect(register)
        self._backend = self.ctx.socket(zmq.REP)
        self._backend.identity = str(os.getpid())
        self._backend.connect(self.backend)
        self.running = False
        self.loop = ioloop.IOLoop()
        self._backstream = zmqstream.ZMQStream(self._backend, self.loop)
        self._backstream.on_recv(self._handle_recv_back)
        self.ping = Stethoscope(heartbeat, onbeatlost=self.lost,
                                delay=ping_delay, retries=ping_retries,
                                ctx=self.ctx)
        self.debug = logger.isEnabledFor(logging.DEBUG)
        self.params = params
        self.pid = os.getpid()
        self.timeout = timeout
        self.max_age = max_age
        self.max_age_delta = max_age_delta
        self.delayed_exit = None
        self.lock = threading.RLock()
        self.env = os.environ.copy()
        self._processes = {}

    def _run(self, args):
        from multiprocessing import Process
        args['slave'] = True
        p = Process(target=functools.partial(run, args))
        p.start()
        self._processes[p.pid] = p
        return p.pid

    def handle(self, message):
        # we get the message from the broker here
        data = message.data
        command = data['command']

        if command in ('RUN', 'SIMULRUN'):
            args = data['args']
            pid = self._run(args)
            return __({'result': {'pid': pid, 'worker_id': str(os.getpid())}})

        elif command == 'STATUS':
            status = {}

            for pid, proc in self._processes.items():
                if proc.is_alive():
                    status[pid] = 'running'
                else:
                    status[pid] = 'terminated'

            return __({'result': status})

        raise NotImplementedError()

    def _handle_recv_back(self, msg):
        # do the message and send the result
        if self.debug:
            logger.debug('Message received')
            target = timed()(self.handle)
        else:
            target = self.handle

        duration = -1

        # results are sent with a PID:OK: or a PID:ERROR prefix
        try:
            res = target(Message.load_from_string(msg[0]))
            if self.debug:
                duration, res = res

            # we're working with strings
            if isinstance(res, unicode):
                res = res.encode('utf8')

            res = '%d:OK:%s' % (self.pid, res)
        except Exception, e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc = traceback.format_tb(exc_traceback)
            exc.insert(0, str(e))
            res = '%d:ERROR:%s' % (self.pid, '\n'.join(exc))
            logger.error(res)

        if self.debug:
            logger.debug('Duration - %.6f' % duration)

        try:
            self._backstream.send(res)
        except Exception:
            logging.error("Could not send back the result", exc_info=True)

    def lost(self):
        logger.info('Master lost ! Quitting..')
        self.running = False
        self.loop.stop()
        return True

    def stop(self):
        """Stops the worker.
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
        logger.debug('Stopping the worker')
        self.running = False
        try:
            self._backstream.flush()
        except zmq.core.error.ZMQError:
            pass
        self.loop.stop()
        self.ping.stop()
        time.sleep(.1)
        self.ctx.destroy(0)
        logger.debug('Worker is stopped')

    def start(self):
        """Starts the worker
        """
        util.PARAMS = self.params
        logger.debug('Starting the worker loop')

        # running the pinger
        self.ping.start()
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

        logger.debug('Worker loop over')


def main(args=sys.argv):
    parser = argparse.ArgumentParser(description='Run some watchers.')

    parser.add_argument('--backend', dest='backend',
                        default=DEFAULT_BACKEND,
                        help="ZMQ socket to the broker.")

    parser.add_argument('--register', dest='register',
                        default=DEFAULT_REG,
                        help="ZMQ socket for the registration.")

    parser.add_argument('--debug', action='store_true', default=False,
                        help="Debug mode")

    parser.add_argument('--logfile', dest='logfile', default='stdout',
                        help="File to log in to.")

    parser.add_argument('--heartbeat', dest='heartbeat',
                        default=DEFAULT_HEARTBEAT,
                        help="ZMQ socket for the heartbeat.")

    parser.add_argument('--params', dest='params', default=None,
                        help='The parameters to be used in the worker.')

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

    logger.info('Agent registers at %s' % args.backend)
    logger.info('The heartbeat socket is at %r' % args.heartbeat)
    agent = Agent(backend=args.backend, heartbeat=args.heartbeat,
                  register=args.register,
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

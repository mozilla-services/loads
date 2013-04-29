""" Jobs runner.
"""
import random
import errno
import sys
import traceback
import argparse
import os
import time
import psutil

from zmq.eventloop import ioloop, zmqstream
import zmq

from loads.util import set_logger, logger
from loads.transport.util import (register_ipc_file, DEFAULT_FRONTEND,
                                  DEFAULT_BACKEND, DEFAULT_HEARTBEAT,
                                  DEFAULT_REG, verify_broker,
                                  kill_ghost_brokers)
from loads.transport.heartbeat import Heartbeat
from loads.transport.exc import DuplicateBrokerError
from loads.transport.client import DEFAULT_TIMEOUT_MOVF


DEFAULT_IOTHREADS = 1


class Broker(object):
    """Class that route jobs to workers.

    Options:

    - **frontend**: the ZMQ socket to receive jobs.
    - **backend**: the ZMQ socket to communicate with workers.
    - **heartbeat**: the ZMQ socket to receive heartbeat requests.
    - **register** : the ZMQ socket to register workers
    """
    def __init__(self, frontend=DEFAULT_FRONTEND, backend=DEFAULT_BACKEND,
                 heartbeat=DEFAULT_HEARTBEAT, register=DEFAULT_REG,
                 io_threads=DEFAULT_IOTHREADS,
                 worker_timeout=DEFAULT_TIMEOUT_MOVF):
        # before doing anything, we verify if a broker is already up and
        # running
        logger.debug('Verifying if there is a running broker')
        pid = verify_broker(frontend)
        if pid is not None:    # oops. can't do this !
            logger.debug('Ooops, we have a running broker on that socket')
            raise DuplicateBrokerError(pid)

        logger.debug('Initializing the broker.')

        for endpoint in (frontend, backend, heartbeat):
            if endpoint.startswith('ipc'):
                register_ipc_file(endpoint)

        self.context = zmq.Context(io_threads=io_threads)

        # setting up the three sockets
        self._frontend = self.context.socket(zmq.ROUTER)
        self._frontend.identity = 'broker-' + frontend
        self._frontend.bind(frontend)
        self._backend = self.context.socket(zmq.ROUTER)
        self._backend.bind(backend)
        self._registration = self.context.socket(zmq.PULL)
        self._registration.bind(register)

        # setting up the streams
        self.loop = ioloop.IOLoop()
        self._frontstream = zmqstream.ZMQStream(self._frontend, self.loop)
        self._frontstream.on_recv(self._handle_recv_front)
        self._backstream = zmqstream.ZMQStream(self._backend, self.loop)
        self._backstream.on_recv(self._handle_recv_back)
        self._regstream = zmqstream.ZMQStream(self._registration, self.loop)
        self._regstream.on_recv(self._handle_reg)

        # heartbeat
        self.pong = Heartbeat(heartbeat, io_loop=self.loop, ctx=self.context)

        # status
        self.started = False
        self.poll_timeout = None

        # workers registration and timers
        self._workers = []
        self._worker_times = {}
        self.worker_timeout = worker_timeout

    def _remove_worker(self, worker_id):
        logger.debug('%r removed' % worker_id)
        self._workers.remove(worker_id)
        if worker_id in self._worker_times:
            del self._worker_times[worker_id]

    def _handle_reg(self, msg):
        if msg[0] == 'REGISTER':
            if msg[1] not in self._workers:
                logger.debug('%r registered' % msg[1])
                self._workers.append(msg[1])
        elif msg[0] == 'UNREGISTER':
            if msg[1] in self._workers:
                self._remove_worker(msg[1])

    def _check_worker(self, worker_id):
        # box-specific, will do better later XXX
        exists = psutil.pid_exists(int(worker_id))
        if not exists:
            logger.debug('The worker %r is gone' % worker_id)
            return False

        if worker_id in self._worker_times:

            start, stop = self._worker_times[worker_id]
            if stop is not None:
                duration = start - stop
                if duration > self.worker_timeout:
                    logger.debug('The worker %r is slow (%.2f)' % (worker_id,
                            duration))
                    return False
        return True

    def _handle_recv_front(self, msg, tentative=0):
        # front => back
        # if the last part of the message is 'PING', we just PONG back
        # this is used as a health check
        if msg[-1] == 'PING':
            self._frontstream.send_multipart(msg[:-1] + [str(os.getpid())])
            return

        #logger.debug('front -> back [choosing a worker]')
        if tentative == 3:
            logger.debug('No workers')
            self._frontstream.send_multipart(msg[:-1] +
                    ['%d:ERROR:No worker' % os.getpid()])
            return

        # we want to decide who's going to do the work
        found_worker = False

        while not found_worker and len(self._workers) > 0:
            worker_id = random.choice(self._workers)
            if not self._check_worker(worker_id):
                self._remove_worker(worker_id)
            else:
                found_worker = True

        if not found_worker:
            logger.debug('No worker, will try later')
            later = time.time() + 0.5 + (tentative * 0.2)
            self.loop.add_timeout(later, lambda: self._handle_recv_front(msg,
                                    tentative + 1))
            return

        # start the timer
        self._worker_times[worker_id] = time.time(), None

        # now we can send to the right guy
        msg.insert(0, worker_id)
        #logger.debug('front -> back [%s]' % worker_id)

        try:
            self._backstream.send_multipart(msg)
        except Exception, e:
            # we don't want to die on error. we just log it
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc = traceback.format_tb(exc_traceback)
            exc.insert(0, str(e))
            logger.error('\n'.join(exc))

    def _handle_recv_back(self, msg):
        # back => front
        #logger.debug('front <- back [%s]' % msg[0])

        # let's remove the worker id and track the time it took
        worker_id = msg[0]
        msg = msg[1:]
        now = time.time()

        if worker_id in self._worker_times:
            start, stop = self._worker_times[worker_id]
            self._worker_times[worker_id] = start, now
        else:
            self._worker_times[worker_id] = now, now

        try:
            self._frontstream.send_multipart(msg)
        except Exception, e:
            # we don't want to die on error. we just log it
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc = traceback.format_tb(exc_traceback)
            exc.insert(0, str(e))
            logger.error('\n'.join(exc))

    def start(self):
        """Starts the broker.
        """
        logger.debug('Starting the loop')
        if self.started:
            return

        # running the heartbeat
        self.pong.start()

        self.started = True
        while self.started:
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

    def stop(self):
        """Stops the broker.
        """
        if not self.started:
            return

        self._backstream.flush()
        logger.debug('Stopping the heartbeat')
        self.pong.stop()
        logger.debug('Stopping the loop')
        self.loop.stop()
        self.started = False
        self.context.destroy(0)


def main(args=sys.argv):
    parser = argparse.ArgumentParser(description='Powerhose broker.')

    parser.add_argument('--frontend', dest='frontend',
                        default=DEFAULT_FRONTEND,
                        help="ZMQ socket to receive jobs.")

    parser.add_argument('--backend', dest='backend',
                        default=DEFAULT_BACKEND,
                        help="ZMQ socket for workers.")

    parser.add_argument('--heartbeat', dest='heartbeat',
                        default=DEFAULT_HEARTBEAT,
                        help="ZMQ socket for the heartbeat.")

    parser.add_argument('--register', dest='register',
                        default=DEFAULT_REG,
                        help="ZMQ socket for the registration.")

    parser.add_argument('--io-threads', type=int,
                        default=DEFAULT_IOTHREADS,
                        help="Number of I/O threads")

    parser.add_argument('--debug', action='store_true', default=False,
                        help="Debug mode")

    parser.add_argument('--check', action='store_true', default=False,
                        help=("Use this option to check if there's a running "
                              " broker. Returns the PID if a broker is up."))

    parser.add_argument('--purge-ghosts', action='store_true', default=False,
                        help="Use this option to purge ghost brokers.")

    parser.add_argument('--logfile', dest='logfile', default='stdout',
                        help="File to log in to .")

    args = parser.parse_args()
    set_logger(args.debug, logfile=args.logfile)

    if args.purge_ghosts:
        broker_pids, ghosts = kill_ghost_brokers(args.frontend)
        if broker_pids is None:
            logger.info('No running broker.')
        else:
            logger.info('The active broker runs at PID: %s' % broker_pids)

        if len(ghosts) == 0:
            logger.info('No ghosts where killed.')
        else:
            logger.info('Ghost(s) killed: %s' \
                    % ', '.join([str(g) for g in ghosts]))
        return 0

    if args.check:
        pid = verify_broker(args.frontend)
        if pid is None:
            logger.info('There seem to be no broker on this endpoint')
        else:
            logger.info('A broker is running. PID: %s' % pid)
        return 0

    logger.info('Starting the broker')
    try:
        broker = Broker(frontend=args.frontend, backend=args.backend,
                        heartbeat=args.heartbeat, register=args.register,
                        io_threads=args.io_threads)
    except DuplicateBrokerError, e:
        logger.info('There is already a broker running on PID %s' % e)
        logger.info('Exiting')
        return 1

    logger.info('Listening to incoming jobs at %r' % args.frontend)
    logger.info('Workers may register at %r' % args.backend)
    logger.info('The heartbeat socket is at %r' % args.heartbeat)
    try:
        broker.start()
    except KeyboardInterrupt:
        pass
    finally:
        broker.stop()

    return 0


if __name__ == '__main__':
    sys.exit(main())

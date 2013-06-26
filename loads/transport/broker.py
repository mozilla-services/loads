""" Jobs runner.
"""
import random
import errno
import sys
import traceback
import argparse
import os
import time
import json
from uuid import uuid4
from collections import defaultdict

import psutil

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from loads.util import set_logger, logger
from loads.transport.util import (register_ipc_file, DEFAULT_FRONTEND,
                                  DEFAULT_BACKEND, DEFAULT_HEARTBEAT,
                                  DEFAULT_REG, verify_broker,
                                  kill_ghost_brokers, DEFAULT_RECEIVER,
                                  DEFAULT_PUBLISHER, extract_result)
from loads.transport.heartbeat import Heartbeat
from loads.transport.exc import DuplicateBrokerError
from loads.transport.client import DEFAULT_TIMEOUT_MOVF
from loads.transport.brokerdb import BrokerDB


DEFAULT_IOTHREADS = 1


class Broker(object):
    """Class that route jobs to workers.

    Options:

    - **frontend**: the ZMQ socket to receive jobs.
    - **backend**: the ZMQ socket to communicate with workers.
    - **heartbeat**: the ZMQ socket to receive heartbeat requests.
    - **register** : the ZMQ socket to register workers.
    - **receiver**: the ZMQ socket that receives data from workers.
    - **publisher**: the ZMQ socket to publish workers data.
    """
    def __init__(self, frontend=DEFAULT_FRONTEND, backend=DEFAULT_BACKEND,
                 heartbeat=DEFAULT_HEARTBEAT, register=DEFAULT_REG,
                 io_threads=DEFAULT_IOTHREADS,
                 worker_timeout=DEFAULT_TIMEOUT_MOVF,
                 receiver=DEFAULT_RECEIVER, publisher=DEFAULT_PUBLISHER):
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

        # setting up the sockets
        self._frontend = self.context.socket(zmq.ROUTER)
        self._frontend.identity = 'broker-' + frontend
        self._frontend.bind(frontend)
        self._backend = self.context.socket(zmq.ROUTER)
        self._backend.bind(backend)
        self._registration = self.context.socket(zmq.PULL)
        self._registration.bind(register)
        self._receiver = self.context.socket(zmq.PULL)
        self._receiver.bind(receiver)
        self._publisher = self.context.socket(zmq.PUB)
        self._publisher.bind(publisher)

        # setting up the streams
        self.loop = ioloop.IOLoop()
        self._frontstream = zmqstream.ZMQStream(self._frontend, self.loop)
        self._frontstream.on_recv(self._handle_recv_front)
        self._backstream = zmqstream.ZMQStream(self._backend, self.loop)
        self._backstream.on_recv(self._handle_recv_back)
        self._regstream = zmqstream.ZMQStream(self._registration, self.loop)
        self._regstream.on_recv(self._handle_reg)
        self._rcvstream = zmqstream.ZMQStream(self._receiver, self.loop)
        self._rcvstream.on_recv(self._handle_rcv)

        # heartbeat
        self.pong = Heartbeat(heartbeat, io_loop=self.loop, ctx=self.context)

        # status
        self.started = False
        self.poll_timeout = None

        # workers registration and timers
        self._workers = []
        self._worker_times = {}
        self.worker_timeout = worker_timeout
        self._runs = {}

        # local DB
        self._db = BrokerDB(self.loop)

    def _remove_worker(self, worker_id):
        logger.debug('%r removed' % worker_id)
        if worker_id in self._workers:
            self._workers.remove(worker_id)

        if worker_id in self._worker_times:
            del self._worker_times[worker_id]

        if worker_id in self._runs:
            del self._runs[worker_id]

    def _handle_rcv(self, msg):
        # publishing all the data received from slaves
        self._publisher.send(msg[0])

        # saving the data locally
        data = json.loads(msg[0])
        worker_id = str(data.get('worker_id'))
        if worker_id in self._runs:
            data['run_id'], data['started'] = self._runs[worker_id]

        self._db.add(data)

    def _handle_reg(self, msg):
        if msg[0] == 'REGISTER':
            if msg[1] not in self._workers:
                logger.debug('%r registered' % msg[1])
                self._workers.append(msg[1])
        elif msg[0] == 'UNREGISTER':
            if msg[1] in self._workers:
                self._remove_worker(msg[1])

    def _associate(self, run_id, workers):
        when = time.time()

        for worker_id in workers:
            self._runs[worker_id] = run_id, when

    def _clean(self):
        # XXX here we want to check out the runs
        # and cleanup _run given the status of the run
        # on each worker
        for worker_id, (run_id, when) in self._runs.items():
            status_msg = ['', json.dumps({'command': 'STATUS',
                                          'run_id': run_id})]

            self._send_to_worker(worker_id, status_msg)


    def _check_worker(self, worker_id):
        # box-specific, will do better later XXX
        exists = psutil.pid_exists(int(worker_id))
        if not exists:
            logger.debug('The worker %r is gone' % worker_id)
            self._remove_worker(worker_id)
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

    def _send_json(self, target, data):
        data = json.dumps(data)
        msg = target + ['%d:OK:%s' % (os.getpid(), data)]
        self._frontstream.send_multipart(msg)

    def _handle_recv_front(self, msg, tentative=0):
        # front => back
        # if the last part of the message is 'PING', we just PONG back
        # this is used as a health check
        data = json.loads(msg[2])
        cmd = data['command']

        if cmd == 'PING':
            res = json.dumps({'result': os.getpid()})
            self._frontstream.send_multipart(msg[:-1] + [res])
            return
        elif cmd == 'LISTRUNS':
            runs = defaultdict(list)
            for worker_id, (run_id, when) in self._runs.items():
                runs[run_id].append((worker_id, when))
            res = json.dumps({'result': runs})
            self._frontstream.send_multipart(msg[:-1] + [res])
            return
        elif cmd == 'STOPRUN':
            workers = []
            run_id = data['run_id']
            for worker_id, (_run_id, when) in self._runs.items():
                if run_id != _run_id:
                    continue
                workers.append(worker_id)

            # now we have a list of workers to stop
            stop_msg = msg[:-1] + [json.dumps({'command': 'STOP'})]

            for worker_id in workers:
                self._send_to_worker(worker_id, stop_msg)

            # we give back the list of workers we stopped
            res = json.dumps({'result': workers})
            self._frontstream.send_multipart(msg[:-1] + [res])

            # and force a clean
            self._clean()
            return
        elif cmd == 'GET_DATA':
            # we send back the data we have in the db
            # XXX stream ?
            db_data = self._db.get_data(data['run_id'])
            res = json.dumps({'result': db_data})
            self._frontstream.send_multipart(msg[:-1] + [res])
            return

        # other commands below this point are for workers
        if tentative == 3:
            logger.debug('No workers')
            msg = msg[:-1] + ['%d:ERROR:No worker' % os.getpid()]
            self._frontstream.send_multipart(msg)
            return

        # the msg tells us which worker to work with
        data = json.loads(msg[2])   # XXX we need to unserialize here

        # broker protocol
        cmd = data['command']

        if cmd == 'LIST':
            # we return a list of worker ids and their status
            self._send_json(msg[:-1], {'result': self._workers})
            return
        elif cmd == 'SIMULRUN':
            if data['agents'] > len(self._workers):
                self._send_json(msg[:-1], {'error': 'Not enough agents'})
                return

            # we want to run the same command on several agents
            # provisionning them
            workers = []
            available = list(self._workers)

            while len(workers) < data['agents']:
                worker_id = random.choice(available)
                if self._check_worker(worker_id):
                    workers.append(worker_id)
                    available.remove(worker_id)

            # create a unique id for this run
            run_id = str(uuid4())
            self._associate(run_id, workers)

            # send to every worker with the run_id
            data['run_id'] = run_id
            msg[2] = json.dumps(data)

            for worker_id in workers:
                self._send_to_worker(worker_id, msg)

            # tell the client what workers where picked
            self._send_json(msg[:-1], {'result': {'workers': workers,
                                                  'run_id': run_id}})
            return

        # regular pass-through == one worker
        if 'worker_id' not in data:
            # we want to decide who's going to do the work
            found_worker = False

            while not found_worker and len(self._workers) > 0:
                worker_id = random.choice(self._workers)
                if self._check_worker(worker_id):
                    found_worker = True

            if not found_worker:
                logger.debug('No worker, will try later')
                later = time.time() + 0.5 + (tentative * 0.2)
                func = self._handle_recv_front
                self.loop.add_timeout(later, lambda: func(msg, tentative + 1))
                return
        else:
            worker_id = str(data['worker_id'])

        # send to a single worker
        self._send_to_worker(worker_id, msg)

    def _send_to_worker(self, worker_id, msg):
        msg = list(msg)

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

        # grabbing the data to update the broker status
        #data = json.loads(extract_result(msg[-1])[-1])['result']
        #if data.get('command') == 'STATUS':
        #    import pdb; pdb.set_trace()
        #print 'received from back ' + str(data)
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

        # running the cleaner
        self.cleaner = ioloop.PeriodicCallback(self._clean, 1000, self.loop)
        #self.cleaner.start()

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

        logger.debug('Stopping the cleaner')
        #self.cleaner.stop()

        logger.debug('Stopping the loop')
        self.loop.stop()

        self.started = False
        self.context.destroy(0)


def main(args=sys.argv):
    parser = argparse.ArgumentParser(description='Loads broker.')

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

    parser.add_argument('--receiver', dest='receiver',
                        default=DEFAULT_RECEIVER,
                        help="ZMQ socket for the registration.")

    parser.add_argument('--publisher', dest='publisher',
                        default=DEFAULT_PUBLISHER,
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
            logger.info('Ghost(s) killed: %s'
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
                        receiver=args.receiver, publisher=args.publisher,
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

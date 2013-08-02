""" Jobs runner.
"""
import errno
import sys
import traceback
import argparse
import os
import json
from uuid import uuid4

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from loads.util import set_logger, logger
from loads.transport.util import (register_ipc_file, DEFAULT_FRONTEND,
                                  DEFAULT_BACKEND, DEFAULT_HEARTBEAT,
                                  DEFAULT_REG, verify_broker,
                                  kill_ghost_brokers,
                                  DEFAULT_BROKER_RECEIVER,
                                  DEFAULT_PUBLISHER)
from loads.transport.heartbeat import Heartbeat
from loads.transport.exc import DuplicateBrokerError
from loads.transport.client import DEFAULT_TIMEOUT_MOVF
from loads.db.brokerdb import DEFAULT_DBDIR
from loads.transport.brokerctrl import BrokerController, NotEnoughWorkersError


DEFAULT_IOTHREADS = 1


class Broker(object):
    """Class that route jobs to workers.

    Options:

    - **frontend**: the ZMQ socket to receive jobs.
    - **backend**: the ZMQ socket to communicate with agents.
    - **heartbeat**: the ZMQ socket to receive heartbeat requests.
    - **register** : the ZMQ socket to register workers.
    - **receiver**: the ZMQ socket that receives data from workers.
    - **publisher**: the ZMQ socket to publish workers data
    """
    def __init__(self, frontend=DEFAULT_FRONTEND, backend=DEFAULT_BACKEND,
                 heartbeat=DEFAULT_HEARTBEAT, register=DEFAULT_REG,
                 io_threads=DEFAULT_IOTHREADS,
                 worker_timeout=DEFAULT_TIMEOUT_MOVF,
                 receiver=DEFAULT_BROKER_RECEIVER, publisher=DEFAULT_PUBLISHER,
                 dbdir=DEFAULT_DBDIR, use_heartbeat=False):
        # before doing anything, we verify if a broker is already up and
        # running
        logger.debug('Verifying if there is a running broker')
        pid = verify_broker(frontend)
        if pid is not None:    # oops. can't do this !
            logger.debug('Ooops, we have a running broker on that socket')
            raise DuplicateBrokerError(pid)

        self.endpoints = {'frontend': frontend,
                          'backend': backend,
                          'heartbeat': heartbeat,
                          'register': register,
                          'receiver': receiver,
                          'publisher': publisher}

        logger.debug('Initializing the broker.')

        for endpoint in self.endpoints.values():
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
        self._rcvstream.on_recv(self._handle_recv)

        # heartbeat
        self.use_heartbeat = use_heartbeat
        if use_heartbeat:
            self.pong = Heartbeat(heartbeat, io_loop=self.loop,
                                  ctx=self.context)

        # status
        self.started = False
        self.poll_timeout = None

        # controller
        self.ctrl = BrokerController(self, self.loop, dbdir, worker_timeout)

    def _handle_recv(self, msg):
        # publishing all the data received from agents
        self._publisher.send(msg[0])

        # saving the data locally
        data = json.loads(msg[0])
        worker_id = str(data.get('worker_id'))
        self.ctrl.save_data(worker_id, data)

    def _handle_reg(self, msg):
        if msg[0] == 'REGISTER':
            self.ctrl.register_worker(msg[1])
        elif msg[0] == 'UNREGISTER':
            self.ctrl.unregister_worker(msg[1])

    def _send_json(self, target, data):
        try:
            self._frontstream.send_multipart(target + [json.dumps(data)])
        except ValueError:
            logger.error('Could not dump %s' % str(data))
            raise

    def _handle_recv_front(self, msg, tentative=0):
        # front => back
        # if the last part of the message is 'PING', we just PONG back
        # this is used as a health check
        data = json.loads(msg[2])
        target = msg[:-1]

        cmd = data['command']
        if cmd == 'PING':
            res = {'result': {'pid': os.getpid(),
                              'endpoints': self.endpoints,
                              'workers': self.ctrl.workers}}
            self._send_json(target, res)
            return
        elif cmd == 'LISTRUNS':
            logger.debug('Asked for LISTRUNS')
            res = {'result': self.ctrl.list_runs()}
            logger.debug('Got %s' % str(res))
            self._send_json(target, res)
            return
        elif cmd == 'STOPRUN':
            run_id = data['run_id']
            stopped_workers = self.ctrl.stop_run(run_id, msg)

            # we give back the list of workers we stopped
            res = {'result': stopped_workers}
            self._send_json(target, res)
            return
        elif cmd == 'GET_DATA':
            # we send back the data we have in the db
            # XXX stream ?
            db_data = self.ctrl.get_data(data['run_id'])
            self._send_json(target, {'result': db_data})
            return
        elif cmd == 'GET_COUNTS':
            counts = self.ctrl.get_counts(data['run_id'])
            self._send_json(target, {'result': counts})
            return
        elif cmd == 'GET_METADATA':
            metadata = self.ctrl.get_metadata(data['run_id'])
            self._send_json(target, {'result': metadata})
            return

        # other commands below this point are for workers
        if tentative == 3:
            logger.debug('No workers')
            self._send_json(target, {'error': 'No worker'})
            return

        # the msg tells us which worker to work with
        data = json.loads(msg[2])   # XXX we need to unserialize here

        # broker protocol
        cmd = data['command']

        if cmd == 'LIST':
            # we return a list of worker ids and their status
            self._send_json(target, {'result': self.ctrl.workers})
            return
        elif cmd == 'RUN':
            # create a unique id for this run
            run_id = str(uuid4())

            # get some workers
            try:
                workers = self.ctrl.reserve_workers(data['agents'], run_id)
            except NotEnoughWorkersError:
                self._send_json(target, {'error': 'Not enough agents'})
                return

            # send to every worker with the run_id and the receiver endpoint
            data['run_id'] = run_id
            data['args']['zmq_receiver'] = self.endpoints['receiver']

            msg[2] = json.dumps(data)

            # save the tests metadata in the db
            self.ctrl.save_metadata(run_id, data['args'])
            self.ctrl.flush_db()

            for worker_id in workers:
                self.ctrl.send_to_worker(worker_id, msg)

            # tell the client what workers where picked
            res = {'result': {'workers': workers, 'run_id': run_id}}
            self._send_json(target, res)
            return

        if 'worker_id' not in data:
            raise NotImplementedError('DEAD CODE?')
        else:
            worker_id = str(data['worker_id'])
            self.ctrl.send_to_worker(worker_id, msg)

    def _handle_recv_back(self, msg):
        # back => front
        #logger.debug('front <- back [%s]' % msg[0])
        # let's remove the worker id and track the time it took
        worker_id = msg[0]
        msg = msg[1:]

        # grabbing the data to update the workers statuses if needed
        data = json.loads(msg[-1])
        if 'error' in data:
            result = data['error']
            logger.error(result.get('exception'))
        else:
            result = data['result']

        if result.get('command') == '_STATUS':
            statuses = result['status'].values()
            run_id = self.ctrl.update_status(worker_id, statuses)
            if run_id is not None:
                # if the tests are finished, publish this on the pubsub.
                self._publisher.send(json.dumps({'data_type': 'run-finished',
                                                 'run_id': run_id}))

            return

        # other things are pass-through
        try:
            self._frontstream.send_multipart(msg)
        except Exception, e:
            logger.error('Could not send to front')
            logger.error(msg)
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
        if self.use_heartbeat:
            self.pong.start()

        # running the cleaner
        self.cleaner = ioloop.PeriodicCallback(self.ctrl.clean,
                                               2500, self.loop)
        self.cleaner.start()

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

        try:
            self._backstream.flush()
        except IOError:
            pass

        if self.use_heartbeat:
            logger.debug('Stopping the heartbeat')
            self.pong.stop()

        logger.debug('Stopping the cleaner')
        self.cleaner.stop()

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
                        default=DEFAULT_BROKER_RECEIVER,
                        help="ZMQ socket to receive events from the runners")

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
                        help="File to log in to.")

    parser.add_argument('--db-directory', dest='dbdir', default=DEFAULT_DBDIR,
                        help="Database Directory.")

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
                        io_threads=args.io_threads, dbdir=args.dbdir)
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

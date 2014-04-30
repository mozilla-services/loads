""" Jobs runner.
"""
import errno
import sys
import traceback
import argparse
import os

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from loads.util import set_logger, logger, json
from loads.transport.util import (register_ipc_file, DEFAULT_FRONTEND,
                                  DEFAULT_BACKEND,
                                  DEFAULT_REG, verify_broker,
                                  DEFAULT_BROKER_RECEIVER,
                                  DEFAULT_PUBLISHER,
                                  DEFAULT_AGENT_TIMEOUT)
from loads.transport.heartbeat import Heartbeat
from loads.transport.exc import DuplicateBrokerError
from loads.db import get_backends
from loads.transport.brokerctrl import BrokerController


DEFAULT_IOTHREADS = 1


class Broker(object):
    """Class that route jobs to agents.

    Options:

    - **frontend**: the ZMQ socket to receive jobs.
    - **backend**: the ZMQ socket to communicate with agents.
    - **heartbeat**: the ZMQ socket to receive heartbeat requests.
    - **register** : the ZMQ socket to register agents.
    - **receiver**: the ZMQ socket that receives data from agents.
    - **publisher**: the ZMQ socket to publish agents data
    """
    def __init__(self, frontend=DEFAULT_FRONTEND, backend=DEFAULT_BACKEND,
                 heartbeat=None, register=DEFAULT_REG,
                 io_threads=DEFAULT_IOTHREADS,
                 agent_timeout=DEFAULT_AGENT_TIMEOUT,
                 receiver=DEFAULT_BROKER_RECEIVER, publisher=DEFAULT_PUBLISHER,
                 db='python', dboptions=None, web_root=None):
        # before doing anything, we verify if a broker is already up and
        # running
        logger.debug('Verifying if there is a running broker')
        pid = verify_broker(frontend)
        if pid is not None:    # oops. can't do this !
            logger.debug('Ooops, we have a running broker on that socket')
            raise DuplicateBrokerError(pid)

        self.endpoints = {'frontend': frontend,
                          'backend': backend,
                          'register': register,
                          'receiver': receiver,
                          'publisher': publisher}

        if heartbeat is not None:
            self.endpoints['heartbeat'] = heartbeat

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
        self.pid = str(os.getpid())
        self._backend.identity = self.pid
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
        if heartbeat is not None:
            self.pong = Heartbeat(heartbeat, io_loop=self.loop,
                                  ctx=self.context,
                                  onregister=self._deregister)
        else:
            self.pong = None

        # status
        self.started = False
        self.poll_timeout = None

        # controller
        self.ctrl = BrokerController(self, self.loop, db=db,
                                     dboptions=dboptions,
                                     agent_timeout=agent_timeout)

        self.web_root = web_root

    def _handle_recv(self, msg):
        # publishing all the data received from agents
        self._publisher.send(msg[0])
        data = json.loads(msg[0])
        agent_id = str(data.get('agent_id'))

        # saving the data locally
        self.ctrl.save_data(agent_id, data)

    def _deregister(self):
        self.ctrl.unregister_agents('asked by the heartbeat.')

    def _handle_reg(self, msg):
        if msg[0] == 'REGISTER':
            self.ctrl.register_agent(json.loads(msg[1]))
        elif msg[0] == 'UNREGISTER':
            self.ctrl.unregister_agent(msg[1], 'asked via UNREGISTER')

    def send_json(self, target, data):
        assert isinstance(target, basestring), target
        msg = [target, '', json.dumps(data)]
        try:
            self._frontstream.send_multipart(msg)
        except ValueError:
            logger.error('Could not dump %s' % str(data))
            raise

    def _handle_recv_front(self, msg, tentative=0):
        """front => back

        All commands starting with CTRL_ are sent to the controller.
        """
        target = msg[0]

        try:
            data = json.loads(msg[-1])
        except ValueError:
            exc = 'Invalid JSON received.'
            logger.exception(exc)
            self.send_json(target, {'error': exc})
            return

        cmd = data['command']

        # a command handled by the controller
        if cmd.startswith('CTRL_'):
            cmd = cmd[len('CTRL_'):]
            logger.debug('calling %s' % cmd)
            try:
                res = self.ctrl.run_command(cmd, msg, data)
            except Exception, e:
                logger.debug('Failed')
                exc_type, exc_value, exc_traceback = sys.exc_info()
                exc = traceback.format_tb(exc_traceback)
                exc.insert(0, str(e))
                self.send_json(target, {'error': exc})
            else:
                # sending back a synchronous result if needed.
                if res is not None:
                    logger.debug('sync success %s' % str(res))
                    self.send_json(target, res)
                else:
                    logger.debug('async success')

        # misc commands
        elif cmd == 'PING':
            res = {'result': {'pid': os.getpid(),
                              'endpoints': self.endpoints,
                              'agents': self.ctrl.agents}}
            self.send_json(target, res)
        elif cmd == 'LIST':
            # we return a list of agent ids and their status
            self.send_json(target, {'result': self.ctrl.agents})
            return
        else:
            self.send_json(target, {'error': 'unknown command %s' % cmd})

    def _handle_recv_back(self, msg):
        # let's remove the agent id and track the time it took
        agent_id = msg[0]
        if len(msg) == 7:
            client_id = msg[4]
        else:
            client_id = None

        # grabbing the data to update the agents statuses if needed
        try:
            data = json.loads(msg[-1])
        except ValueError:
            logger.error("Could not load the received message")
            logger.error(str(msg))
            return

        if 'error' in data:
            result = data['error']
        else:
            result = data['result']

        command = result.get('command')

        # results from commands sent by the broker
        if command in ('_STATUS', 'STOP', 'QUIT'):
            run_id = self.ctrl.update_status(agent_id, result)

            if run_id is not None:
                # if the tests are finished, publish this on the pubsub.
                self._publisher.send(json.dumps({'data_type': 'run-finished',
                                                 'run_id': run_id}))
            return

        # other things are pass-through (asked by a client)
        if client_id is None:
            return

        try:
            self._frontstream.send_multipart([client_id, '', msg[-1]])
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
        if self.pong is not None:
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

        if self.pong is not None:
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
                        help="ZMQ socket for agents.")

    parser.add_argument('--heartbeat', dest='heartbeat',
                        default=None,
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

    parser.add_argument('--logfile', dest='logfile', default='stdout',
                        help="File to log in to.")

    parser.add_argument('--db', dest='db', default='python',
                        help="Database backend.")

    parser.add_argument('--web-root', help='Root url of the web dashboard.',
                        type=str, default=None)

    # add db args
    for backend, options in get_backends():
        for option, default, help, type_ in options:
            option = 'db_%s_%s' % (backend, option)
            kargs = {'dest': option, 'default': default}

            if type_ is bool:
                kargs['action'] = 'store_true'
            else:
                kargs['type'] = type_

            option = option.replace('_', '-')
            parser.add_argument('--%s' % option, **kargs)

    args = parser.parse_args()
    set_logger(args.debug, logfile=args.logfile)

    if args.check:
        pid = verify_broker(args.frontend)
        if pid is None:
            logger.info('There seem to be no broker on this endpoint')
        else:
            logger.info('A broker is running. PID: %s' % pid)
        return 0

    # grabbing the db options
    dboptions = {}
    prefix = 'db_%s_' % args.db

    for key, value in args._get_kwargs():

        if not key.startswith(prefix):
            continue
        dboptions[key[len(prefix):]] = value

    logger.info('Starting the broker')
    try:
        broker = Broker(frontend=args.frontend, backend=args.backend,
                        heartbeat=args.heartbeat, register=args.register,
                        receiver=args.receiver, publisher=args.publisher,
                        io_threads=args.io_threads, db=args.db,
                        dboptions=dboptions, web_root=args.web_root)
    except DuplicateBrokerError, e:
        logger.info('There is already a broker running on PID %s' % e)
        logger.info('Exiting')
        return 1

    logger.info('Listening to incoming jobs at %r' % args.frontend)
    logger.info('Workers may register at %r' % args.backend)
    if args.heartbeat is not None:
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

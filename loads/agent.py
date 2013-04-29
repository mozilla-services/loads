""" The agent does several things:

- maintains a connection to a master
- gets load testing orders & performs them
- sends back the results in RT
"""
import sys
import argparse
import os
import json
import functools

#from gevent.subprocess import Popen, PIPE
#import gevent
import psutil

from loads.runner import run
from loads.util import set_logger, logger
from loads.transport.worker import (Worker, DEFAULT_BACKEND,
                                    DEFAULT_HEARTBEAT, DEFAULT_REG,
                                    DEFAULT_TIMEOUT_MOVF, DEFAULT_MAX_AGE,
                                    DEFAULT_MAX_AGE_DELTA)


__ = json.dumps


class Agent(Worker):

    def __init__(self, backend=DEFAULT_BACKEND,
                 heartbeat=DEFAULT_HEARTBEAT, register=DEFAULT_REG,
                 ping_delay=10., ping_retries=3,
                 params=None, timeout=DEFAULT_TIMEOUT_MOVF,
                 max_age=DEFAULT_MAX_AGE, max_age_delta=DEFAULT_MAX_AGE_DELTA):

        Worker.__init__(self, self.handle, backend, heartbeat, register,
                        ping_delay,
                        ping_retries, params, timeout, max_age, max_age_delta)
        self.env = os.environ.copy()
        self._processes = {}

    def _run(self, fqnd, concurrency, numruns, stream):
        from multiprocessing import Process
        p = Process(target=functools.partial(run, fqnd, concurrency, numruns,
            stream))
        p.start()
        self._processes[p.pid] = p
        return p.pid

    def handle(self, message):
        # we get the message from the broker here
        data = message.data
        command = data['command']

        if command == 'RUN':
            fqnd = data['fqnd']
            concurrency = data.get('concurrency', 1)
            numruns = data.get('numruns', 1)
            stream = data.get('stream', 'stdout')
            pid = self._run(fqnd, concurrency, numruns, stream)
            return __({'result': {'pid': pid, 'worker_id': str(os.getpid())}})

        elif command == 'STATUS':
            pid = data['pid']
            if self._processes[pid].is_alive():
                return __({'result': 'running'})
            else:
                return __({'result': 'terminated'})

        raise NotImplementedError()


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

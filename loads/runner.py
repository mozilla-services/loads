# runs a functional test or a load test
import unittest
import argparse
import sys
import json
from datetime import datetime

from gevent.pool import Group
import gevent

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from loads.util import resolve_name
from loads.stream import (set_global_stream, stream_list, StdStream,
                          get_global_stream)
from loads import __version__
from loads.transport.client import Client
from loads.transport.util import DEFAULT_FRONTEND


class Runner(object):
    """The tests runner.

    Runs the given test suite. It has two modes:

    - "slave", where results are sent via a ZMQ endpoint
    - "classical", where the results are sent to stdout.
    """
    def __init__(self, args):
        self.args = args
        self.total, self.cycles, self.users, self.agents =\
                self._compute_arguments(args)
        self.fqn = args['fqn']
        self.test = resolve_name(self.fqn)
        self.slave = 'slave' in args

        # slave mode, results sent via ZMQ
        if self.slave:
            self.stream = self.args['stream'] = 'zmq'
            set_global_stream('zmq', self.args)
            # the test results are collected from ZMQ
            self.test_result = get_global_stream()

        # classical one-node mode
        else:
            self.stream = args.get('stream', 'stdout')
            if self.stream == 'stdout':
                args['stream_stdout_total'] = self.total
            set_global_stream(self.stream, args)
            self.test_result = unittest.TestResult()

    def execute(self):
        result = self._execute()

        # XXX Don't remove the other errors here?
        if len(result.errors) > 0:
            error = result.errors[0]
        elif len(result.failures) > 0:
            error = result.failures[0]
        else:
            error = None

        if error is not None:
            tb = error[-1]
            print tb
            return 1
        else:
            return 0

    def _run(self, num, test, cycles, user):
        for cycle in cycles:
            for current_cycle in range(cycle):
                test(self.test_result, cycle, user, current_cycle + 1)
                gevent.sleep(0)

    def _compute_arguments(self, args):
        """
        Read the given :param args: and builds up the total number of runs, the
        number of cycles, users and agents to use.

        Returns a tuple of (total, cycles, users, agents).
        """
        users = args.get('users', '1')
        cycles = args.get('cycles', '1')
        users = [int(user) for user in users.split(':')]
        cycles = [int(cycle) for cycle in cycles.split(':')]
        agents = args.get('agents', 1)
        total = 0
        for user in users:
            total += sum([cycle * user for cycle in cycles])
        if agents is not None:
            total *= agents
        return total, cycles, users, agents

    def _execute(self):
        """Spawn as many greenlets as asked, each of them will call the :method
        _run:

        Wait for all of them to be done and finish.
        """
        from gevent import monkey
        monkey.patch_all()

        klass = self.test.im_class
        ob = klass(self.test.__name__)
        for user in self.users:
            group = Group()
            for i in range(user):
                group.spawn(self._run, i, ob, self.cycles, user)
            group.join()

        gevent.sleep(.1)
        return self.test_result


class DistributedRunner(Runner):
    """ Runner that distributes the load on a cluster and collects results via
    ZMQ.
    """
    def __init__(self, args):
        super(DistributedRunner, self).__init__(args)
        self.ended = self.hits = 0
        self.loop = None
        # local echo
        self.echo = StdStream({'stream_stdout_total': self.total})
        context = zmq.Context()
        self.pull = context.socket(zmq.PULL)
        self.pull.setsockopt(zmq.HWM, 8096 * 4)
        self.pull.setsockopt(zmq.SWAP, 200*2**10)
        self.pull.setsockopt(zmq.LINGER, 1000)
        self.pull.bind(self.args['stream_zmq_endpoint'])

        # io loop
        self.loop = ioloop.IOLoop()
        self.zstream = zmqstream.ZMQStream(self.pull, self.loop)
        self.zstream.on_recv(self._recv_result)

    def _recv_result(self, msg):
        data = json.loads(msg[0])
        if 'test_start' in data:
            pass
        elif 'test_stop' in data:
            self.ended += 1
        elif 'test_success' in data:
            pass
        elif 'failure' in data:
            self.test_result.failures.append((None, data['failure']))
            self.test_result._mirrorOutput = True
        elif 'error' in data:
            self.test_result.failures.append((None, data['error']))
            self.test_result._mirrorOutput = True
        else:
            # XXX this is not the right total (hits vs tests) XXX
            self.hits += 1
            started = data['started']
            data['started'] = datetime.strptime(started,
                                                '%Y-%m-%dT%H:%M:%S.%f')
            self.echo.push(data)

        if self.ended == self.total:
            self.loop.stop()

    def _execute(self):
        # calling the clients now
        client = Client(self.args['broker'])
        client.run(self.args)
        self.loop.start()
        return self.test_result


def run(args):
    if args.get('agents') is None or args.get('slave'):
        return Runner(args).execute()
    else:
        return DistributedRunner(args).execute()


def main():
    parser = argparse.ArgumentParser(description='Runs a load test.')
    parser.add_argument('fqn', help='Fully qualified name of the test',
                        nargs='?')

    parser.add_argument('-u', '--users', help='Number of virtual users',
                        type=str, default='1')

    parser.add_argument('-c', '--cycles', help='Number of cycles per users',
                        type=str, default='1')

    parser.add_argument('--version', action='store_true', default=False,
                        help='Displays Loads version and exits.')

    parser.add_argument('-a', '--agents', help='Number of agents to use',
                        type=int)

    parser.add_argument('-b', '--broker', help='Broker endpoint',
                        default=DEFAULT_FRONTEND)

    parser.add_argument('-s', '--slave', action='store_true',
                        help='Run in slave mode', default=False)

    streams = [st.name for st in stream_list()]
    streams.sort()

    parser.add_argument('--stream', default='stdout',
                        help='The stream that receives the results',
                        choices=streams)

    # per-stream options
    for stream in stream_list():
        for option, value in stream.options.items():
            help, type_, default, cli = value
            if not cli:
                continue

            kw = {'help': help, 'type': type_}
            if default is not None:
                kw['default'] = default

            parser.add_argument('--stream-%s-%s' % (stream.name, option),
                                **kw)

    args = parser.parse_args()

    if args.version:
        print(__version__)
        sys.exit(0)

    if args.fqn is None:
        parser.print_usage()
        sys.exit(0)

    args = dict(args._get_kwargs())
    return run(args)


if __name__ == '__main__':
    sys.exit(main())

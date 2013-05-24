# runs a functional test or a load test
import argparse
import sys
import json
import logging
import traceback

import gevent

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from loads.util import resolve_name
from loads.test_result import TestResult
from loads.relay import ZMQRelay
from loads.output import output_list, create_output

from loads import __version__
from loads.transport.client import Client
from loads.transport.util import DEFAULT_FRONTEND


class Runner(object):
    """The local tests runner.

    It can be run in two different modes:

    - The "classical" mode, where the results are collected locally
    - The "slave" mode, where results are sent to a ZMQ endpoint, to be
      collected on the other side of the pipe (the Distributed runner
      implements the other part of the pipe).
    """
    def __init__(self, args):
        self.args = args
        self.fqn = args['fqn']
        self.test = resolve_name(self.fqn)
        self.slave = 'slave' in args
        self.outputs = []

        (self.total, self.cycles,
         self.users, self.agents) = _compute_arguments(args)

        args['total'] = self.total

        # If we are in slave mode, set the test_result to a 0mq relay
        if self.slave:
            self.test_result = ZMQRelay(self.args)

        # The normal behavior is to collect the results locally.
        else:
            self.test_result = TestResult()

        output = args.get('output', 'stdout')
        self.register_output(output, args)

    def register_output(self, output_name, args):
        output = create_output(output_name, self.test_result, args)
        self.outputs.append(output)
        self.test_result.add_observer(output)

    def execute(self):
        self._execute()
        if self.test_result.has_errors:
            return 1
        return 0

    def _run(self, num, test, cycles, user):
        for cycle in cycles:
            for current_cycle in range(cycle):
                test(cycle=cycle,
                     user=user,
                     current_cycle=current_cycle + 1)
                gevent.sleep(0)

    def _execute(self):
        """Spawn as many greenlets as asked, each of them will call the :method
        _run:

        Wait for all of them to be done and finish.
        """
        from gevent import monkey
        monkey.patch_all()

        if not hasattr(self.test, 'im_class'):
            raise ValueError(self.test)

        # creating the test case instance
        klass = self.test.im_class
        ob = klass(self.test.__name__, self.test_result)

        for user in self.users:
            group = [gevent.spawn(self._run, i, ob, self.cycles, user)
                     for i in range(user)]

            gevent.joinall(group)

        gevent.sleep(0)

        # be sure we flush the outputs that need it.
        for output in self.outputs:
            if hasattr(output, 'flush'):
                output.flush()



class DistributedRunner(Runner):
    """ Runner distributing the load on a cluster of agents, collecting the
    results via ZMQ.

    The runner need to have agents already running. It will send them commands
    trought the zmq pipeline and get back their results, which will be
    in turn sent to the local test_result.
    """
    def __init__(self, args):
        super(DistributedRunner, self).__init__(args)
        self.ended = self.hits = 0
        self.loop = None
        self.test_result = TestResult()

        context = zmq.Context()
        self.pull = context.socket(zmq.PULL)
        self.pull.setsockopt(zmq.HWM, 8096 * 4)
        self.pull.setsockopt(zmq.SWAP, 200 * 2 ** 10)
        self.pull.setsockopt(zmq.LINGER, 1000)
        self.pull.bind(self.args['zmq_endpoint'])

        # io loop
        self.loop = ioloop.IOLoop()
        self.zstream = zmqstream.ZMQStream(self.pull, self.loop)
        self.zstream.on_recv(self._recv_result)

        # XXX Add the output as observers to the test_result
        self.outputs = []

    def _recv_result(self, msg):
        """When we receive some data from zeromq, send it to the test_result
           for later use."""
        data = json.loads(msg[0])
        data_type = data.pop('data_type')

        method = getattr(self.test_result, data_type)
        method(**data)

        # XXX Ask the test_result if everything is finished
        # The previous version was like that:
        # if self.ended == self.total:
        #     self.loop.stop()

    def _execute(self):
        # calling the clients now
        client = Client(self.args['broker'])
        client.run(self.args)
        self.loop.start()
        return self.test_result


def _compute_arguments(args):
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


def run(args):
    if args.get('agents') is None or args.get('slave'):
        try:
            return Runner(args).execute()
        except Exception:
            print traceback.format_exc()
            raise
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

    parser.add_argument('--test-runner', default=None,
                        help='The path to binary to use as the test runner. ' +
                             'The default is this runner')

    parser.add_argument('--zmq-endpoint', default='tcp://127.0.0.1:5558',
                        help='Socket to send the results to')

    outputs = [st.name for st in output_list()]
    outputs.sort()

    parser.add_argument('--output', default='stdout',
                        help='The output used to display the results',
                        choices=outputs)

    # per-output options
    for output in output_list():
        for option, value in output.options.items():
            help, type_, default, cli = value
            if not cli:
                continue

            kw = {'help': help, 'type': type_}
            if default is not None:
                kw['default'] = default

            parser.add_argument('--output-%s-%s' % (output.name, option),
                                **kw)

    args = parser.parse_args()

    wslogger = logging.getLogger('ws4py')
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    wslogger.addHandler(ch)

    if args.version:
        print(__version__)
        sys.exit(0)

    if args.fqn is None:
        parser.print_usage()
        sys.exit(0)

    args = dict(args._get_kwargs())
    res = run(args)
    return res


if __name__ == '__main__':
    sys.exit(main())

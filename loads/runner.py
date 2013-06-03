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
    """Local tests runner.

    Runs in parallel a number of tests and pass the results to the outputs.

    It can be run in two different modes:

    - "Classical" mode: Results are collected and passed to the outputs.
    - "Slave" mode: Results are sent to a ZMQ endpoint and no output is called.
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
        if (not self.slave and
                self.test_result.nb_errors + self.test_result.nb_failures):
            return 1
        return 0

    def _run(self, num, test, cycles, user):
        for cycle in cycles:
            for current_cycle in range(cycle):
                loads_status = (cycle, user, current_cycle + 1, num)
                test(loads_status=loads_status)
                gevent.sleep(0)

    def _execute(self):
        """Spawn all the tests needed and wait for them to finish.
        """
        from gevent import monkey
        monkey.patch_all()

        if not hasattr(self.test, 'im_class'):
            raise ValueError(self.test)

        # creating the test case instance
        klass = self.test.im_class
        ob = klass(test_name=self.test.__name__,
                   test_result=self.test_result,
                   server_url=self.args['server_url'])

        worker_id = self.args.get('worker_id', None)
        self.test_result.startTestRun(worker_id)
        for user in self.users:
            group = [gevent.spawn(self._run, i, ob, self.cycles, user)
                     for i in range(user)]

            gevent.joinall(group)

        gevent.sleep(0)
        self.test_result.stopTestRun(worker_id)

        # be sure we flush the outputs that need it.
        # but do it only if we are in "normal" mode
        if not self.slave:
            self.flush()
        else:
            # in slave mode, be sure to close the zmq relay.
            self.test_result.close()

    def flush(self):
        for output in self.outputs:
            if hasattr(output, 'flush'):
                output.flush()


class DistributedRunner(Runner):
    """Test runner distributing the load on a cluster of agents, collecting the
    results via a ZMQ stream.

    The runner need to have agents already up and running. It will send them
    commands trough the ZMQ pipeline and get back their results, which will be
    in turn sent to the local test_result object.
    """
    def __init__(self, args):
        super(DistributedRunner, self).__init__(args)
        self.ended = self.hits = 0
        self.loop = None
        self.test_result = TestResult()

        self.context = zmq.Context()
        self.pull = self.context.socket(zmq.PULL)
        self.pull.set_hwm(8096 * 10)
        self.pull.setsockopt(zmq.LINGER, -1)
        self.pull.bind(self.args['zmq_endpoint'])

        # io loop
        self.loop = ioloop.IOLoop()
        self.zstream = zmqstream.ZMQStream(self.pull, self.loop)
        self.zstream.on_recv(self._recv_result)

        self.outputs = []

        output = args.get('output', 'stdout')
        self.register_output(output, args)

    def _recv_result(self, msg):
        """When we receive some data from zeromq, send it to the test_result
           for later use."""
        self.loop.add_callback(self._process_result, msg)

    def _process_result(self, msg):
        data = json.loads(msg[0])
        data_type = data.pop('data_type')
        #wid = data.pop('worker_id')
        # XXX Do something with the WID we get back here.

        method = getattr(self.test_result, data_type)
        method(**data)

        if self.test_result.nb_finished_tests == self.total:
            self.loop.stop()

    def _execute(self):
        # calling the clients now
        self.test_result.startTestRun()
        client = Client(self.args['broker'])
        client.run(self.args)
        self.loop.start()
        self.test_result.stopTestRun()
        # end..
        self.context.destroy()
        self.flush()


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
                        help='The path to binary to use as the test runner '
                             'when in distributed mode. The default is '
                             'this runner')

    parser.add_argument('--server-url', default=None,
                        help='The URL of the server you want to test. It '
                             'will override any value your provided in '
                             'the tests for the WebTest client.')

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

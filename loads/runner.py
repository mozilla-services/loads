# runs a functional test or a load test
import argparse
import sys
import json
import logging
import traceback
import os

import gevent

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from konfig import Config

from loads.util import resolve_name, logger, set_logger
from loads.test_result import TestResult
from loads.relay import ZMQRelay
from loads.output import output_list, create_output

from loads import __version__
from loads.transport.client import Client
from loads.transport.util import (DEFAULT_FRONTEND, DEFAULT_RECEIVER,
                                  DEFAULT_PUBLISHER)


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
        self.stop = False

        (self.total, self.cycles,
         self.duration, self.users, self.agents) = _compute_arguments(args)

        self.args['cycles'] = self.cycles
        self.args['users'] = self.users
        self.args['agents'] = self.agents
        self.args['total'] = self.total

        # If we are in slave mode, set the test_result to a 0mq relay
        if self.slave:
            self.test_result = ZMQRelay(self.args)

        # The normal behavior is to collect the results locally.
        else:
            self.test_result = TestResult(args=self.args)

        if not self.slave:
            for output in self.args.get('output', ['stdout']):
                self.register_output(output)

    def register_output(self, output_name):
        output = create_output(output_name, self.test_result, self.args)
        self.outputs.append(output)
        self.test_result.add_observer(output)

    def execute(self):
        self.running = True
        try:
            self._execute()
            if (not self.slave and
                    self.test_result.nb_errors + self.test_result.nb_failures):
                return 1
            return 0
        finally:
            self.running = False

    def _run(self, num, test, user):
        if self.stop:
            return

        if self.duration is None:
            for cycle in self.cycles:
                for current_cycle in range(cycle):
                    loads_status = cycle, user, current_cycle + 1, num
                    test(loads_status=loads_status)
                    gevent.sleep(0)
        else:
            # duration-based
            timeout = gevent.Timeout(self.duration)
            timeout.start()
            try:
                while True and not self.stop:
                    loads_status = 0, user, 0, num
                    test(loads_status=loads_status)
                    gevent.sleep(0)
            except (gevent.Timeout, KeyboardInterrupt):
                pass
            finally:
                self.stop = True
                timeout.cancel()

    def _execute(self):
        """Spawn all the tests needed and wait for them to finish.
        """
        try:
            from gevent import monkey
            monkey.patch_all()

            if not hasattr(self.test, 'im_class'):
                raise ValueError(self.test)

            # creating the test case instance
            klass = self.test.im_class
            ob = klass(test_name=self.test.__name__,
                       test_result=self.test_result,
                       server_url=self.args.get('server_url'))

            worker_id = self.args.get('worker_id', None)

            gevent.spawn(self._grefresh)
            self.test_result.startTestRun(worker_id)

            for user in self.users:
                if self.stop:
                    break

                group = [gevent.spawn(self._run, i, ob, user)
                         for i in range(user)]
                gevent.joinall(group)

            gevent.sleep(0)
            self.test_result.stopTestRun(worker_id)
        except KeyboardInterrupt:
            pass
        finally:
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

    def refresh(self):
        for output in self.outputs:
            if hasattr(output, 'refresh'):
                output.refresh()

    def _grefresh(self):
        self.refresh()
        if not self.stop:
            gevent.spawn_later(.1, self._grefresh)


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

        # socket where the results are published
        self.context = zmq.Context()
        self.pull = self.context.socket(zmq.SUB)
        self.pull.setsockopt(zmq.SUBSCRIBE, '')
        self.pull.set_hwm(8096 * 10)
        self.pull.setsockopt(zmq.LINGER, -1)
        self.pull.connect(self.args.get('zmq_publisher', DEFAULT_PUBLISHER))

        # io loop
        self.loop = ioloop.IOLoop()
        self.zstream = zmqstream.ZMQStream(self.pull, self.loop)
        self.zstream.on_recv(self._recv_result)
        self.outputs = []

        outputs = args.get('output', ['stdout'])

        for output in outputs:
            self.register_output(output)

    def _recv_result(self, msg):
        """When we receive some data from zeromq, send it to the test_result
           for later use."""
        self.loop.add_callback(self._process_result, msg)

    def _process_result(self, msg):
        try:
            data = json.loads(msg[0])
            data_type = data.pop('data_type')

            method = getattr(self.test_result, data_type)
            method(**data)

            if data_type == 'stopTestRun':
                self.loop.stop()
        except KeyboardInterrupt:
            self.loop.stop()

    def _execute(self):
        # calling the clients now
        self.test_result.startTestRun()

        cb = ioloop.PeriodicCallback(self.refresh, 100, self.loop)
        cb.start()
        try:
            client = Client(self.args['broker'])
            logger.debug('Calling the broker...')
            client.run(self.args)
            logger.debug('Waiting for results')
            self.loop.start()
        except KeyboardInterrupt:
            pass
        finally:
            # end..
            cb.stop()
            self.test_result.stopTestRun()
            self.context.destroy()
            self.flush()


def _compute_arguments(args):
    """
    Read the given :param args: and builds up the total number of runs, the
    number of cycles, duration, users and agents to use.

    Returns a tuple of (total, cycles, duration, users, agents).
    """
    users = args.get('users', '1')
    if isinstance(users, str):
        users = users.split(':')
    users = [int(user) for user in users]
    cycles = args.get('cycles')
    duration = args.get('duration')
    if duration is None and cycles is None:
        cycles = '1'

    if cycles is not None:
        if not isinstance(cycles, list):
            cycles = [int(cycle) for cycle in cycles.split(':')]

    agents = args.get('agents', 1)

    # XXX duration based == no total
    total = 0
    if duration is None:
        for user in users:
            total += sum([cycle * user for cycle in cycles])
        if agents is not None:
            total *= agents

    return total, cycles, duration, users, agents


def run(args):
    if args.get('agents') is None or args.get('slave'):
        try:
            return Runner(args).execute()
        except Exception:
            print traceback.format_exc()
            raise
    else:
        logger.debug('Summoning %d agents' % args['agents'])
        return DistributedRunner(args).execute()


def main(sysargs=None):
    if sysargs is None:
        sysargs = sys.argv[1:]

    parser = argparse.ArgumentParser(description='Runs a load test.')
    parser.add_argument('fqn', help='Fully qualified name of the test',
                        nargs='?')

    parser.add_argument('--config', help='Configuration file to read',
                        type=str, default=None)

    parser.add_argument('-u', '--users', help='Number of virtual users',
                        type=str, default='1')

    # loads works with cycles or duration
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-c', '--cycles', help='Number of cycles per users',
                       type=str, default=None)
    group.add_argument('-d', '--duration', help='Duration of the test (s)',
                       type=int, default=None)

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

    parser.add_argument('--zmq-receiver', default=DEFAULT_RECEIVER,
                        help='Socket where the agents send the results to.')

    parser.add_argument('--zmq-publisher', default=DEFAULT_PUBLISHER,
                        help='Socket where the results are published.')

    outputs = [st.name for st in output_list()]
    outputs.sort()

    parser.add_argument('--quiet', action='store_true', default=False)
    parser.add_argument('--output', action='append', default=['stdout'],
                        help='The output used to display the results',
                        choices=outputs)

    parser.add_argument('--aws-image-id', help='Amazon Server Id', type=str,
                        default='ami-be77e08e')
    parser.add_argument('--aws-access-key', help='Amazon Access Key',
                        type=str, default=os.environ.get('ACCESS_KEY'))
    parser.add_argument('--aws-secret-key', help='Amazon Secret Key',
                        type=str, default=os.environ.get('SECRET_KEY'))
    parser.add_argument('--aws-ssh-user', help='Amazon User',
                        type=str, default='ubuntu')
    parser.add_argument('--aws-ssh-key', help='Amazon SSH Key file',
                        type=str, default='ubuntu')
    parser.add_argument('--aws', help='Running on AWS?', action='store_true',
                        default=False)

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

    args = parser.parse_args(sysargs)

    if args.config is not None:
        # second pass !
        config = Config(args.config)
        config_args = config.scan_args(parser, strip_prefixes=['loads'])
        args = parser.parse_args(args=sysargs+config_args)

    if args.quiet and 'stdout' in args.output:
        args.output.remove('stdout')

    # loggers setting
    wslogger = logging.getLogger('ws4py')
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    wslogger.addHandler(ch)
    set_logger()

    if args.version:
        print(__version__)
        sys.exit(0)

    if args.fqn is None:
        parser.print_usage()
        sys.exit(0)

    # deploy on amazon
    if args.aws:
        from loads.deploy import aws_deploy
        master, master_id = aws_deploy(args.aws_access_key,
                                       args.aws_secret_key,
                                       args.aws_ssh_user,
                                       args.aws_ssh_key,
                                       args.aws_image_id)
        # XXX
        args.broker = 'tcp://%s:5553' % master['host']
        args.zmq_publisher = 'tcp://%s:5554' % master['host']
    else:
        master_id = None

    try:
        args = dict(args._get_kwargs())
        res = run(args)
        return res
    finally:
        if master_id is not None:
            print 'Shutting down Amazon boxes'
            from loads.deploy import aws_shutdown
            aws_shutdown(args['aws_access_key'],
                         args['aws_secret_key'],
                         master_id)


if __name__ == '__main__':
    sys.exit(main())

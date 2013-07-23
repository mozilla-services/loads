import argparse
import sys
import logging
import traceback
import os
from datetime import datetime

from konfig import Config

from loads.util import logger, set_logger, try_import
from loads.output import output_list
from loads import __version__
from loads.transport.util import (DEFAULT_FRONTEND, DEFAULT_RECEIVER,
                                  DEFAULT_PUBLISHER)
from loads.runner import Runner
from loads.distributed import DistributedRunner
from loads.transport.client import Client


def _detach_question(runner):
    res = ''
    while res not in ('s', 'd'):
        res = raw_input('Do you want to (s)top the test or (d)etach ? ')
        res = res.lower().strip()
        if len(res) > 1:
            res = res[0]
    if res == 's':
        runner.cancel()


def run(args):
    is_slave = args.get('slave', False)
    has_agents = args.get('agents', None)
    attach = args.get('attach', False)
    if not attach and (is_slave or not has_agents):
        try:
            return Runner(args).execute()
        except Exception:
            print traceback.format_exc()
            raise
    else:
        runner = DistributedRunner(args)

        if attach:
            # find out what's running
            client = Client(args['broker'])
            runs = client.list_runs()

            if len(runs) == 0:
                raise ValueError("Nothing is running")
            elif len(runs) == 1:
                run_id, run_data = runs.items()[0]
                __, started = run_data[-1]
            else:
                # we need to pick one
                raise NotImplementedError()

            counts = client.get_counts(run_id)
            metadata = client.get_metadata(run_id)

            logger.debug('Reattaching run %r' % run_id)
            started = datetime.utcfromtimestamp(started)
            try:
                return runner.attach(run_id, started, counts, metadata)
            except KeyboardInterrupt:
                _detach_question(runner)
        else:
            logger.debug('Summoning %d agents' % args['agents'])

            try:
                return runner.execute()
            except KeyboardInterrupt:
                _detach_question(runner)


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

    # loads works with hits or duration
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--hits', help='Number of hits per users',
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
    parser.add_argument('--aws-python-deps', help='Python deps to install',
                        action='append', default=[])
    parser.add_argument('--aws-system-deps', help='System deps to install',
                        action='append', default=[])
    parser.add_argument('--aws-test-dir', help='Test dir to embark',
                        default=None)

    parser.add_argument('--attach', help='Reattach to a run',
                        action='store_true', default=False)

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
        args = parser.parse_args(args=sysargs + config_args)

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

    if args.fqn is None and not args.attach:
        parser.print_usage()
        sys.exit(0)

    # deploy on amazon
    if args.aws:
        try_import('paramiko', 'boto')

        from loads.deploy import aws_deploy
        master, master_id = aws_deploy(args.aws_access_key,
                                       args.aws_secret_key,
                                       args.aws_ssh_user,
                                       args.aws_ssh_key,
                                       args.aws_image_id,
                                       args.aws_python_deps,
                                       args.aws_system_deps,
                                       args.aws_test_dir)
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

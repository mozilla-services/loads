import argparse
import sys
import logging
import traceback
from datetime import datetime

from konfig import Config

from loads.util import logger, set_logger
from loads.output import output_list
from loads import __version__
from loads.transport.util import DEFAULT_FRONTEND, DEFAULT_PUBLISHER
from loads.runner import Runner
from loads.distributed import DistributedRunner
from loads.transport.client import Client, TimeoutError


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

        if attach:
            # find out what's running
            client = Client(args['broker'])
            try:
                runs = client.list_runs()
            except TimeoutError:
                logger.info("Can't reach the broker at %r" % args['broker'])
                client.close()
                return 1

            if len(runs) == 0:
                logger.info("Nothing seem to be running on that broker.")
                client.close()
                return 1
            elif len(runs) == 1:
                run_id, run_data = runs.items()[0]
                __, started = run_data[-1]
            else:
                # we need to pick one
                raise NotImplementedError()

            counts = client.get_counts(run_id)
            events = [event for event, hits in counts]

            if 'stopTestRun' in events:
                logger.info("This test has just stopped.")
                client.close()
                return 1

            metadata = client.get_metadata(run_id)
            logger.debug('Reattaching run %r' % run_id)
            started = datetime.utcfromtimestamp(started)
            runner = DistributedRunner(args)
            try:
                return runner.attach(run_id, started, counts, metadata)
            except KeyboardInterrupt:
                _detach_question(runner)
        else:
            logger.debug('Summoning %d agents' % args['agents'])
            runner = DistributedRunner(args)
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

    parser.add_argument('--test-dir', help='Directory to run the test from',
                        type=str, default=None)

    parser.add_argument('--python-dep', help='Python dep to install',
                        action='append', default=[])

    parser.add_argument('--include-file',
                        help='File(s) to include - glob-style',
                        action='append', default=[])

    # loads works with hits or duration
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--hits', help='Number of hits per users',
                       type=str, default=None)
    group.add_argument('-d', '--duration', help='Duration of the test (s)',
                       type=int, default=None)

    parser.add_argument('--version', action='store_true', default=False,
                        help='Displays Loads version and exits.')

    parser.add_argument('--ping-broker', action='store_true', default=False,
                        help='Displays info about the broker and exits.')

    parser.add_argument('--purge-broker', action='store_true', default=False,
                        help='Stops all runs on the broker and exits.')

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

    parser.add_argument('--zmq-receiver', default=None,
                        help=('Socket where the runners send the events to'
                              ' (the one opened on the agent side).'))

    parser.add_argument('--zmq-publisher', default=DEFAULT_PUBLISHER,
                        help='Socket where the results are published.')

    parser.add_argument('--observer', action='append',
                        help='Callable that will receive the final results.')

    outputs = [st.name for st in output_list()]
    outputs.sort()

    parser.add_argument('--quiet', action='store_true', default=False)
    parser.add_argument('--output', action='append', default=['stdout'],
                        help='The output used to display the results',
                        choices=outputs)

    parser.add_argument('--cwd', default=None,
                        help='The base directory to run the tests from')

    parser.add_argument('--attach', help='Reattach to a run',
                        action='store_true', default=False)

    parser.add_argument('--detach', help='Detach immediatly',
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
        if 'fqn' in config['loads']:
            config_args += [config['loads']['fqn']]
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

    if args.ping_broker:
        client = Client(args.broker)
        res = client.ping()
        print('Broker running on pid %d' % res['pid'])
        print('%d workers registered' % len(res['workers']))
        print('endpoints:')
        for name, location in res['endpoints'].items():
            print('  - %s: %s' % (name, location))

        runs = client.list_runs()
        if len(runs) == 0:
            print('Nothing is running right now.')
        else:
            print('We have %d run(s) right now:' % len(runs))
            for run_id, workers in runs.items():
                print('  - %s with %d worker(s)' % (run_id, len(workers)))
        sys.exit(0)

    if args.purge_broker:
        client = Client(args.broker)
        runs = client.list_runs()
        if len(runs) == 0:
            print('Nothing to purge.')
        else:
            print('We have %d run(s) right now:' % len(runs))

            for run_id, workers in runs.items():
                print('Purging %s...' % run_id)
                client.stop_run(run_id)

            print('Purged.')

        sys.exit(0)



    if args.fqn is None and not args.attach:
        parser.print_usage()
        sys.exit(0)

    args = dict(args._get_kwargs())
    res = run(args)
    return res


if __name__ == '__main__':
    sys.exit(main())

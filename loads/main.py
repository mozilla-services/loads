import argparse
import logging
import sys
import traceback
from datetime import datetime

from konfig import Config

from loads import __version__
from loads.output import output_list
from loads.runners import (LocalRunner, DistributedRunner, ExternalRunner,
                           RUNNERS)
from loads.transport.client import Client, TimeoutError
from loads.transport.util import (DEFAULT_FRONTEND, DEFAULT_PUBLISHER,
                                  DEFAULT_SSH_FRONTEND)
from loads.util import logger, set_logger
from loads.observers import observers


def _detach_question(runner):
    res = ''
    while res not in ('s', 'd'):
        res = raw_input('Do you want to (s)top the test or (d)etach ? ')
        res = res.lower().strip()
        if len(res) > 1:
            res = res[0]
    if res == 's':
        runner.cancel()


def add_options(items, parser, fmt):
    """Read the list of items and add options to the parser using the given
    format.

    :param items:
        A list of class objects to iterate over. They should contain at least
        a name and an options argument.

    :param parser:
        The parser object from argparse.

    :param fmt:
        The format to use for the option to add to the parser. It should
        contain {name} and {option}, for instance '--output-{name}-{option}' is
        a valid format.
    """
    for item in items:
        for option, value in item.options.items():
            help_, type_, default, cli = value
            if not cli:
                continue

            kw = {'help': help_, 'type': type_}
            if default is not None:
                kw['default'] = default

            parser.add_argument(fmt.format(name=item.name, option=option),
                                **kw)


def run(args):
    is_slave = args.get('slave', False)
    has_agents = args.get('agents', None)
    attach = args.get('attach', False)
    if not attach and (is_slave or not has_agents):
        if args.get('test_runner', None) is not None:
            runner = ExternalRunner
        else:
            runner = LocalRunner
        try:
            return runner(args).execute()
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


def _parse(sysargs=None):
    if sysargs is None:
        sysargs = sys.argv[1:]

    parser = argparse.ArgumentParser(description='Runs a load test.')
    parser.add_argument('fqn', help='Fully Qualified Name of the test',
                        nargs='?')

    parser.add_argument('--config', help='Configuration file to read',
                        type=str, default=None)

    parser.add_argument('-u', '--users', help='Number of virtual users',
                        type=str, default='1')

    parser.add_argument('--test-dir', help='Directory to run the test from',
                        type=str, default=None)

    parser.add_argument('--python-dep', help='Python (PyPI) dependencies '
                                             'to install',
                        action='append', default=[])

    parser.add_argument('--include-file',
                        help='File(s) to include (needed for the test) '
                             '- glob-style',
                        action='append', default=[])

    parser.add_argument('--ssh', help='SSH tunnel - e.g. user@server:port',
                        type=str, default=None)

    # loads works with hits or duration
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--hits', help='Number of hits per user',
                       type=str, default=None)
    group.add_argument('-d', '--duration', help='Duration of the test (s)',
                       type=int, default=None)

    parser.add_argument('--version', action='store_true', default=False,
                        help='Displays Loads version and exits.')

    parser.add_argument('--test-runner', default=None,
                        help='The path to binary to use as the test runner '
                             'when in distributed mode. The default is '
                             'this (python) runner')

    parser.add_argument('--server-url', default=None,
                        help='The URL of the server you want to test. It '
                             'will override any value your provided in '
                             'the tests for the WebTest client.')

    parser.add_argument('--observer', action='append',
                        choices=[observer.name for observer in observers],
                        help='Callable that will receive the final results. '
                             'Only in distributed mode (runs on the broker)')

    #
    # Loading observers options
    #
    for observer in observers:
        prefix = '--observer-%s-' % observer.name
        for option in observer.options:
            name = prefix + option['name']
            parser.add_argument(name, help=option.get('help'),
                                default=option.get('default'),
                                type=option.get('type'),
                                action=option.get('action'))

    parser.add_argument('--no-patching',
                        help='Deactivate Gevent monkey patching.',
                        action='store_true', default=False)

    parser.add_argument('--project-name', help='Project name.',
                        default='N/A')

    #
    # distributed options
    #
    parser.add_argument('-a', '--agents', help='Number of agents to use.',
                        type=int)

    parser.add_argument('--zmq-receiver', default=None,
                        help=('ZMQ socket where the runners send the events to'
                              ' (opened on the agent side).'))

    parser.add_argument('--zmq-publisher', default=DEFAULT_PUBLISHER,
                        help='ZMQ socket where the test results messages '
                             'are published.')

    parser.add_argument('--ping-broker', action='store_true', default=False,
                        help='Pings the broker to get info, display it and '
                             'exits.')

    parser.add_argument('--check-cluster', action='store_true', default=False,
                        help='Runs a test on all agents then exits.')

    parser.add_argument('--purge-broker', action='store_true', default=False,
                        help='Stops all runs on the broker and exits.')

    parser.add_argument('-b', '--broker', help='Broker endpoint',
                        default=DEFAULT_FRONTEND)

    parser.add_argument('--user-id', help='Name of the user who runs the test',
                        type=str, default='undefined')

    outputs = [st.name for st in output_list()]
    outputs.sort()

    parser.add_argument('--quiet', action='store_true', default=False,
                        help='Do not print any log messages.')
    parser.add_argument('--output', action='append', default=['stdout'],
                        help='The output which will get the results',
                        choices=outputs)

    parser.add_argument('--attach', help='Reattach to a distributed run',
                        action='store_true', default=False)

    parser.add_argument('--detach', help='Detach immediatly the current '
                                         'distributed run',
                        action='store_true', default=False)

    # Adds the per-output and per-runner options.
    add_options(RUNNERS, parser, fmt='--{name}-{option}')
    add_options(output_list(), parser, fmt='--output-{name}-{option}')

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

    return args, parser


def main(sysargs=None):
    # parsing the command line
    args, parser = _parse(sysargs)

    # loggers setting
    wslogger = logging.getLogger('ws4py')
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    wslogger.addHandler(ch)
    set_logger()

    if args.version:
        print(__version__)
        sys.exit(0)

    if args.ssh:
        if args.broker == DEFAULT_FRONTEND:
            args.broker = DEFAULT_SSH_FRONTEND

        # control that we have pexpect
        try:
            import pexpect    # NOQA
        except ImportError:
            print("To use --ssh you need pexpect")
            print("Try: pip install pexpect")
            sys.exit(0)

    if args.ping_broker or args.purge_broker or args.check_cluster:

        client = Client(args.broker, ssh=args.ssh)
        ping = client.ping()

        if args.purge_broker:
            runs = client.purge_broker()
            if len(runs) == 0:
                print('Nothing to purge.')
            else:
                print('We have %d run(s) right now:' % len(runs))
                print('Purged.')
            sys.exit(0)

        elif args.ping_broker:
            print('Broker running on pid %d' % ping['pid'])
            print('%d agents registered' % len(ping['agents']))
            print('endpoints:')
            for name, location in ping['endpoints'].items():
                print('  - %s: %s' % (name, location))

            runs = client.list_runs()
            if len(runs) == 0:
                print('Nothing is running right now.')
            else:
                print('We have %d run(s) right now:' % len(runs))
                for run_id, agents in runs.items():
                    print('  - %s with %d agent(s)' % (run_id, len(agents)))
            sys.exit(0)

        elif args.check_cluster:
            total_agents = len(ping['agents'])
            runs = client.list_runs().items()
            busy_agents = sum([len(agents) for run_id, agents in runs])
            avail = total_agents - busy_agents
            if avail == 0:
                # no agents are available.
                print('All agents are busy.')
                sys.exit(0)

            args.fqn = 'loads.examples.test_blog.TestWebSite.test_health'
            args.agents = avail
            args.hits = '1'
            print('Running a health check on all %d agents' % args.agents)

    # if we don't have an fqn or we're not attached, something's wrong
    if args.fqn is None and not args.attach:
        parser.print_usage()
        sys.exit(0)

    args = dict(args._get_kwargs())
    res = run(args)
    return res

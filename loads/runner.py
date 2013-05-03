# runs a functional test or a load test
import unittest
import argparse
import sys
import time

from gevent.pool import Group
import gevent

from loads.util import resolve_name
from loads.stream import set_global_stream, stream_list
from loads import __version__
from loads.client import LoadsClient
from loads.transport.util import DEFAULT_FRONTEND


def _run(num, test, test_result, numruns):
    for i in range(numruns):
        test(test_result)
        gevent.sleep(0)


def run(args):
    """ Runs a test.
    """
    from gevent import monkey
    monkey.patch_all()

    stream = args['stream']
    if stream == 'stdout':
        args['stream_stdout_total'] = concurrency * numruns

    set_global_stream(stream, args)
    test = resolve_name(args['fqn'])
    klass = test.im_class
    ob = klass(test.__name__)
    test_result = unittest.TestResult()

    group = Group()

    for i in range(args['users']):
        group.spawn(_run, i, ob, test_result, args['cycles'])

    group.join()

    return  test_result


def distributed_run(args):
    # XXX deal with agents
    client = LoadsClient(args['broker'])
    res = client.run(args)
    pid = res['pid']
    worker_id = res['worker_id']
    status = client.status(worker_id, pid)
    print status

    while status == 'running':
        time.sleep(1.)
        status = client.status(worker_id, pid)
        print status


def main():
    parser = argparse.ArgumentParser(description='Runs a load test.')
    parser.add_argument('fqn', help='Fully qualified name of the test',
                         nargs='?')

    parser.add_argument('-u', '--users', help='Number of virtual users',
                        type=int, default=1)

    parser.add_argument('-c', '--cycles', help='Number of cycles per users',
                        type=int, default=1)

    parser.add_argument('--version', action='store_true', default=False,
                        help='Displays Loads version and exits.')

    parser.add_argument('-a', '--agents', help='Number of agents to use',
                        type=int)
    parser.add_argument('-b', '--broker', help='Broker endpoint',
                        default=DEFAULT_FRONTEND)

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

    if args.get('agents') is None:
        # direct run
        #
        result = run(args)
        print
        print result
    else:
        # distributed run
        # contact the broker and send the load
        result = distributed_run(args)
        print
        print result

if __name__ == '__main__':
    main()

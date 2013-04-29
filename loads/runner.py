# runs a functional test or a load test
import unittest
import argparse
import sys

from gevent.pool import Group
import gevent

from loads.util import resolve_name
from loads.stream import set_global_stream
from loads import __version__


def _run(num, test, test_result, numruns):
    for i in range(numruns):
        test(test_result)
        gevent.sleep(0)


def run(fqn, concurrency=1, numruns=1, stream='stdout',
        stream_args=None):
    """ Runs a test.

    * fnq: fully qualified name
    * concurrency: number of concurrent runs
    * numruns: number of run per concurrent
    """
    from gevent import monkey
    monkey.patch_all()

    if stream_args is None:
        if stream == 'stdout':
            stream_args = {'total': concurrency * numruns}
        else:
            stream_args = {}

    set_global_stream(stream, **stream_args)
    test = resolve_name(fqn)
    klass = test.im_class
    ob = klass(test.__name__)
    test_result = unittest.TestResult()

    group = Group()

    for i in range(concurrency):
        group.spawn(_run, i, ob, test_result, numruns)

    group.join()

    return  test_result


def main():
    parser = argparse.ArgumentParser(description='Runs a load test.')
    parser.add_argument('fqnd', help='Fully qualified name of the test',
                         nargs='?')

    parser.add_argument('-u', '--users', help='Number of virtual users',
                        type=int, default=1)

    parser.add_argument('-c', '--cycles', help='Number of cycles per users',
                        type=int, default=1)

    parser.add_argument('--version', action='store_true', default=False,
                        help='Displays Loads version and exits.')

    parser.add_argument('--stream', default='stdout',
                        help='The stream that receives the results')


    args = parser.parse_args()

    if args.version:
        print(__version__)
        sys.exit(0)

    if args.fqnd is None:
        parser.print_usage()
        sys.exit(0)

    result = run(args.fqnd, args.users, args.cycles, args.stream)
    print
    print result


if __name__ == '__main__':
    main()

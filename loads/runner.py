# runs a functional test or a load test
import unittest

from gevent.pool import Group
import gevent

from loads.util import resolve_name
import sys
from loads.stream import set_global_stream


def _run(num, test, test_result, numruns):
    for i in range(numruns):
        test(test_result)
        gevent.sleep(0)


def run(fqn, concurrency=1, numruns=1):
    """ Runs a test.

    * fnq: fully qualified name
    * concurrency: number of concurrent runs
    * numruns: number of run per concurrent
    """
    set_global_stream('stdout', total=concurrency * numruns)
    test = resolve_name(fqn)
    klass = test.im_class
    ob = klass(test.__name__)
    test_result = unittest.TestResult()

    group = Group()

    for i in range(concurrency):
        group.spawn(_run, i, ob, test_result, numruns)

    group.join()

    return  test_result


if __name__ == '__main__':
    from gevent import monkey
    monkey.patch_all()
    result = run('loads.examples.test_blog.TestWebSite.test_something', 10, 100)
    print
    print result

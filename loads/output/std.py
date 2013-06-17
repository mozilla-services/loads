import sys
import time
import traceback

import gevent


class StdOutput(object):
    name = 'stdout'
    options = {'total': ('Total Number of items', int, None, False),
               'duration': ('Duration', int, None, False)}

    def __init__(self, test_result, args):
        self.results = test_result
        self.args = args
        self.current = 0
        self.starting = None

    def flush(self):
        write = sys.stdout.write
        write("\nHits: %d" % self.results.nb_hits)
        write("\nStarted: %s" % self.results.start_time)
        write("\nDuration: %.2f seconds" % self.results.duration)
        write("\nApproximate Average RPS: %d" %
              self.results.requests_per_second())
        write("\nAverage request time: %.2fs" %
              self.results.average_request_time())
        write("\nOpened web sockets: %d" % self.results.sockets)
        write("\nBytes received via web sockets : %d\n" %
              self.results.socket_data_received)
        write("\nSuccess: %d" % self.results.nb_success)
        write("\nErrors: %d" % self.results.nb_errors)
        write("\nFailures: %d" % self.results.nb_failures)
        write("\n\n")

        if self.results.nb_errors:
            self._print_tb(self.results.errors)

        if self.results.nb_failures:
            self._print_tb(self.results.failures)

        sys.stdout.flush()
        sys.stderr.flush()

    def _print_tb(self, data):
        data = data.next()
        if len(data) == 0:
            return
        exc_class, exc, tb = data[0]
        if isinstance(exc_class, basestring):
            name = exc_class
        else:
            name = exc_class.__name__
        sys.stderr.write("\n%s: %s" % (name, exc))
        if tb is not None:
            sys.stderr.write("\n Traceback: \n")
            traceback.print_tb(tb, sys.stderr)

    def _duration_progress(self):
        age = time.time() - self.starting
        percent = int(float(age) / float(self.args['duration'])
                      * 100.)
        bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
        sys.stdout.write("\r%s %d%%" % (bar, percent))
        sys.stdout.flush()
        gl = gevent.Greenlet(self._duration_progress)
        gl.start_later(.05)   # refresh time

    def push(self, method_called, *args, **data):
        """Collect data in real time and make make the progress bar progress"""
        duration = self.args['duration']

        # duration-based
        if method_called == 'startTestRun' and duration is not None:
            if self.starting is None:
                self.starting = time.time()
                self._duration_progress()

        # count-based
        elif method_called == 'stopTest' and duration is None:
            percent = int(float(self.results.nb_finished_tests)
                          / float(self.args['total']) * 100.)
            bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
            sys.stdout.write("\r%s %d%%" % (bar, percent))

        sys.stdout.flush()

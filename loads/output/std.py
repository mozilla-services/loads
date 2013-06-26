import sys
import random
import traceback
from loads.relay import ZMQRelay


class StdOutput(object):
    name = 'stdout'
    options = {'total': ('Total Number of items', int, None, False),
               'duration': ('Duration', int, None, False)}

    def __init__(self, test_result, args):
        self.results = test_result
        self.args = args
        self.pos = self.current = 0
        self.starting = None

    def flush(self):
        write = sys.stdout.write
        self._duration_progress()
        write("\nDuration: %.2f seconds" % self.results.duration)

        if self.args.get('attach'):
            write('\n')
            sys.stdout.flush()
            sys.stderr.flush()
            return

        write("\nHits: %d" % self.results.nb_hits)
        write("\nStarted: %s" % self.results.start_time)
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

    def refresh(self):
        if isinstance(self.results, ZMQRelay):
            return
        self._duration_progress()

    def _duration_progress(self):
        if self.args.get('attach'):
            self.pos += 1
            before = ' ' * self.pos
            after = ' ' * (24 - self.pos)
            bar = '[' + before + '=' + after + ']'
            sys.stdout.write("\r%s" % bar)
            sys.stdout.flush()
            if self.pos == 24:
                self.pos = 0
            return

        duration = self.args.get('duration')
        if duration is not None:
            percent = int(float(self.results.duration)
                          / float(duration) * 100.)
        else:
            percent = int(float(self.results.nb_finished_tests)
                          / float(self.args['total']) * 100.)

        if percent >= 100:
            percent = 100

        bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
        sys.stdout.write("\r%s %d%%" % (bar, percent))
        sys.stdout.flush()

    def push(self, method_called, *args, **data):
        pass

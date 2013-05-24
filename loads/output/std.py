import sys
import traceback


class StdOutput(object):
    name = 'stdout'
    options = {'total': ('Total Number of items', int, None, False)}

    def __init__(self, test_result, args):
        self.results = test_result
        self.args = args

    def flush(self):
        write = sys.stdout.write
        write("\nHits: %d" % self.results.nb_hits)
        write("\nStarted: %s" % self.results.start_time)
        write("\nDuration: %.2f seconds" % self.results.duration)
        write("\nApproximate Average RPS: %d" %
                self.results.average_request_time())
        write("\nOpened web sockets: %d" % self.results.sockets)
        write("\nBytes received via web sockets : %d\n" %
                         self.results.socket_data_received)
        write("\nSuccess: %d" % self.results.nb_success)
        write("\nErrors: %d" % self.results.nb_errors)
        write("\nFailures: %d" % self.results.nb_failures)

        write("\n\n")

        if self.results.nb_errors:
            exc_class, exc, tb = self.results.errors.next()[0]
            sys.stderr.write(str(exc))
            sys.stderr.write("\n Traceback: \n")

            traceback.print_tb(tb, sys.stderr)

        if self.results.nb_failures:
            write(self.results.failures.next())

        sys.stdout.flush()
        sys.stderr.flush()

    def push(self, method, *args, **data):
        if method == 'add_hit':
            percent = int(float(data['current'])
                          / float(self.args['total']) * 100.)
            bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
            sys.stdout.write("\r%s %d%%" % (bar, percent))
        sys.stdout.flush()

import array
import sys
import traceback

from loads.relay import ZMQRelay


def get_terminal_width(fd=1):
    """Get the width for the given pty fd (default is TTY1)."""
    if sys.platform == 'win32':
        return 100

    import termios
    import fcntl
    sizebuf = array.array('h', [0, 0])
    fcntl.ioctl(fd, termios.TIOCGWINSZ, sizebuf, True)
    return sizebuf[1]


def get_screen_relative_value(percent, terminal_width):
    """Convert a percentage into a value relative to the width of the screen"""
    return int(round(percent * (terminal_width / 100.))) - 8


class StdOutput(object):
    name = 'stdout'
    options = {'total': ('Total Number of items', int, None, False),
               'duration': ('Duration', int, None, False)}

    def __init__(self, test_result, args):
        self.results = test_result
        self.args = args
        self.pos = self.current = 0
        self.starting = None
        self._terminal_width = get_terminal_width()

    def flush(self):
        write = sys.stdout.write
        self._duration_progress()
        write("\nDuration: %.2f seconds" % self.results.duration)
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

        if tb not in (None, ''):   # XXX fix this
            sys.stderr.write("\n Traceback: \n")
            traceback.print_tb(tb, sys.stderr)

    def refresh(self):
        if isinstance(self.results, ZMQRelay):
            return
        self._duration_progress()

    def _duration_progress(self):
        duration = self.args.get('duration')
        if duration is not None:
            percent = int(float(self.results.duration)
                          / float(duration) * 100.)
        else:
            percent = int(float(self.results.nb_finished_tests)
                          / float(self.args['total']) * 100.)

        if percent > 100:
            percent = 100

        rel_percent = get_screen_relative_value(percent, self._terminal_width)

        bar = '[' + ('=' * rel_percent).ljust(self._terminal_width - 8) + ']'
        out = "\r%s %s%%" % (bar, str(percent).rjust(3))
        sys.stdout.write(out)
        sys.stdout.flush()

    def push(self, method_called, *args, **data):
        pass

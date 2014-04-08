import array
import sys
import traceback
from collections import defaultdict

from loads.results import ZMQTestResult


def get_terminal_width(fd=1):
    """Get the width for the given pty fd (default is TTY1)."""
    if sys.platform == 'win32':
        return 100

    import termios
    import fcntl
    sizebuf = array.array('h', [0, 0])
    try:
        fcntl.ioctl(fd, termios.TIOCGWINSZ, sizebuf, True)
    except IOError:
        return 100
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
        write("\nOpened web sockets: %d" % self.results.opened_sockets)
        write("\nBytes received via web sockets : %d\n" %
              self.results.socket_data_received)
        write("\nSuccess: %d" % self.results.nb_success)
        write("\nErrors: %d" % self.results.nb_errors)
        write("\nFailures: %d" % self.results.nb_failures)
        write("\n\n")

        if self.results.nb_errors:
            self._print_tb(self.results.errors)
            write('\n')

        if self.results.nb_failures:
            self._print_tb(self.results.failures)
            write('\n')

        avt = 'average_request_time'

        def _metric(item1, item2):
            return - cmp(item1[-1][avt], item2[-1][avt])

        metrics = [(url, metric)
                   for url, metric in self.results.get_url_metrics().items()]
        metrics.sort(_metric)

        if len(metrics) > 0:
            slowest = metrics[0]
            write("\nSlowest URL: %s \tAverage Request Time: %s" %
                  (slowest[0], slowest[1][avt]))

            if len(metrics) > 10:
                write("\n\nStats by URLs (10 slowests):")
                metrics = metrics[:10]
            else:
                write("\n\nStats by URLs:")

            longer_url = max([len(url) for url, metric in metrics])

            for url, metric in metrics:
                spacing = (longer_url - len(url)) * ' '
                write("\n- %s%s\t" % (url, spacing))
                res = []
                for name, value in metric.items():
                    res.append("%s: %s" % (name.replace('_', ' ').capitalize(),
                                           value))
                write('%s' % '\t'.join(res))

        write('\n')
        counters = self.results.get_counters()
        if len(counters) > 0:
            write("\nCustom metrics:")
            for name, value in counters.items():
                write("\n- %s : %s" % (name, value))

            write('\n')

        sys.stdout.flush()
        sys.stderr.flush()

    def _print_tb(self, data):
        # 3 most commons
        errors = defaultdict(int)

        for line in data:
            if len(line) == 0:
                continue

            exc_class, exc_, tb_ = line[0]

            if isinstance(exc_class, basestring):
                name_ = exc_class
            else:
                name_ = exc_class.__name__

            errors[name_, exc_, tb_] += 1

        errors = [(count, name, exc, tb) for (name, exc, tb), count
                  in errors.items()]
        errors.sort()

        for count, name, exc, tb in errors[:3]:
            sys.stderr.write("%d occurrences of: \n" % count)
            sys.stderr.write("    %s: %s" % (name, exc))

            if tb in (None, ''):   # XXX fix this
                sys.stderr.write('\n')
            else:
                if isinstance(tb, basestring):
                    sys.stderr.write(tb.replace('\n', '    \n'))
                else:
                    sys.stderr.write("    Traceback: \n")
                    traceback.print_tb(tb, file=sys.stderr)

    def refresh(self, run_id=None):
        if isinstance(self.results, ZMQTestResult):
            return
        self._duration_progress(run_id)

    def _duration_progress(self, run_id=None):
        if run_id is not None:
            self.results.sync(run_id)
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

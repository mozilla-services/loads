import sys


class StdStream(object):
    name = 'stdout'
    options = {'total': ('Total Number of items', int, None, False)}

    def __init__(self, args):
        self.current = 0
        self.total = args['stream_stdout_total']
        self.start = None
        self.end = None

    def push(self, data):
        date = data['started']
        if self.start is None:
            self.start = self.end = date
        else:
            if date < self.start:
                self.start = date
            elif date > self.end:
                self.end = date
        self.current += 1
        percent = int(float(self.current) / float(self.total) * 100.)
        bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
        sys.stdout.write("\r%s %d%%" % (bar, percent))

        if self.current == self.total:
            seconds = (self.end - self.start).total_seconds()
            if seconds == 0:
                rps = self.total
            else:
                rps = float(self.total) / seconds
            sys.stdout.write("\nHits: %d" % self.total)
            sys.stdout.write("\nStarted: %s" % self.start)
            sys.stdout.write("\nDuration: %.2f seconds" % seconds)
            sys.stdout.write("\nApproximate Average RPS: %d\n" % rps)

        sys.stdout.flush()

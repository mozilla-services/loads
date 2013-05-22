import sys


class StdOutput(object):
    name = 'stdout'
    options = {'total': ('Total Number of items', int, None, False)}

    def __init__(self, collector, args):
        self.collector = collector
        self.args = args

    def flush(self):
        sys.stdout.write("\nHits: %d" % self.collector.nb_hits)
        sys.stdout.write("\nStarted: %s" % self.collector.start_time)
        sys.stdout.write("\nDuration: %.2f seconds" % self.collector.duration)
        sys.stdout.write("\nApproximate Average RPS: %d"
                         % self.collector.average_request_time)
        sys.stdout.write("\nOpened web sockets: %d" % self.collector.sockets)
        sys.stdout.write("\nBytes received via web sockets : %d\n" %
                         self.collector.socket_data_received)
        sys.stdout.flush()

    def push(self, method, **data):
        percent = int(float(self.collector.current)
                      / float(self.collector.total) * 100.)
        bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
        sys.stdout.write("\r%s %d%%" % (bar, percent))
        sys.stdout.flush()

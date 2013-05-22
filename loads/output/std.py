import sys


class StdOutput(object):
    name = 'stdout'
    options = {'total': ('Total Number of items', int, None, False)}

    def __init__(self, test_result, args):
        self.test_result = test_result
        self.args = args

    def flush(self):
        sys.stdout.write("\nHits: %d" % self.test_result.nb_hits)
        sys.stdout.write("\nStarted: %s" % self.test_result.start_time)
        sys.stdout.write("\nDuration: %.2f seconds" % self.test_result.duration)
        sys.stdout.write("\nApproximate Average RPS: %d"
                         % self.test_result.average_request_time)
        sys.stdout.write("\nOpened web sockets: %d" % self.test_result.sockets)
        sys.stdout.write("\nBytes received via web sockets : %d\n" %
                         self.test_result.socket_data_received)
        sys.stdout.flush()

    def push(self, method, **data):
        if method == 'add_hit':
            percent = int(float(data['current'])
                          / float(self.args['total']) * 100.)
            bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
            sys.stdout.write("\r%s %d%%" % (bar, percent))
        sys.stdout.flush()

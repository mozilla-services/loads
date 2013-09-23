from collections import defaultdict

from loads.results import TestResult
from loads.transport.client import Client


class RemoteTestResult(TestResult):
    """ This version does not store all data

    RemoteTestResult interacts with the broker to fetch the data when its APIs
    are called.
    """
    def __init__(self, config=None, args=None):
        super(RemoteTestResult, self).__init__(config, args)
        self.counts = defaultdict(int)
        self.run_id = None
        if args is None:
            self.args = {}

    def __getattribute__(self, name):
        properties = {'nb_finished_tests': 'stopTest',
                      'nb_hits': 'add_hit',
                      'nb_failures': 'addFailure',
                      'nb_errors': 'addError',
                      'nb_success': 'addSuccess',
                      'nb_tests': 'startTest',
                      'socket': 'socket_open',
                      'socket_data_received': 'socket_message'}

        values = ('errors', 'failures')

        if name in properties:
            return self.counts[properties[name]]
        elif name in values:
            if self.args.get('agents') is None:
                raise NotImplementedError(name)
            return self._get_values(name)

        return TestResult.__getattribute__(self, name)

    def set_counts(self, counts):
        self.counts.update(counts)

    def _get_values(self, name):
        """Calls the broker to get the errors or failures.
        """
        if name in 'failures':
            key = 'addFailure'
        elif name == 'errors':
            key = 'addError'

        client = Client(self.args['broker'])

        for line in client.get_data(self.run_id, data_type=key):
            line = line['exc_info']
            yield [line]

    def sync(self, run_id):
        if self.args.get('agents') is None:
            return

        self.run_id = run_id

        # we're asking the broker about the latest counts
        self.counts = defaultdict(int)

        client = Client(self.args['broker'])
        for line in client.get_data(run_id, groupby=True):
            self.counts[line['data_type']] += line['count']

from unittest import TestResult
import zmq.green as zmq
from loads.util import DateTimeJSONEncoder


class ZMQStream(object):
    """Writes everything you send to it to a zmq endpoint.

    Also used as the test result class.
    """
    name = 'zmq'
    options = {'endpoint': ('Socket to send the results to',
                            str, 'tcp://127.0.0.1:5558', True)}

    def __init__(self, args):
        self.context = zmq.Context()
        self._push = self.context.socket(zmq.PUSH)
        self._push.setsockopt(zmq.HWM, 8096 * 4)
        self._push.setsockopt(zmq.SWAP, 200*2**10)
        self._push.setsockopt(zmq.LINGER, 1000)
        self._push.connect(args.get('stream_zmq_endpoint',
                                    'tcp://127.0.0.1:5558'))
        self.encoder = DateTimeJSONEncoder()
        self._result = TestResult()
        self.errors = []
        self.failures = []
        self.args = args
        self.wid = self.args['worker_id']

    # unittest.TestResult APIS
    def startTest(self, test, cycle, user, current_cycle):
        self.push({'test_start': str(test),
                   'cycle': cycle,
                   'user': user,
                   'current_cycle': current_cycle,
                   'worker_id': self.wid})

    def stopTest(self, test, cycle, user, current_cycle):
        self.push({'test_stop': str(test),
                   'cycle': cycle,
                   'user': user,
                   'current_cycle': current_cycle,
                   'worker_id': self.wid})

    def addFailure(self, test, failure, cycle, user, current_cycle):
        exc_info = self._result._exc_info_to_string(failure, test)
        self.failures.append((test, exc_info))
        self.push({'failure': exc_info,
                   'cycle': cycle,
                   'user': user,
                   'current_cycle': current_cycle,
                   'worker_id': self.wid})

    def addError(self, test, error, cycle, user, current_cycle):
        exc_info = self._result._exc_info_to_string(error, test)
        self.errors.append((test, exc_info))
        self.push({'error': exc_info,
                   'cycle': cycle,
                   'user': user,
                   'current_cycle': current_cycle,
                   'worker_id': self.wid})

    def addSuccess(self, test, cycle, user, current_cycle):
        self.push({'test_success': str(test),
                   'cycle': cycle,
                   'user': user,
                   'current_cycle': current_cycle,
                   'worker_id': self.wid})

    def flush(self):
        pass

    # ZMQ push
    def push(self, data):
        self._push.send(self.encoder.encode(data), zmq.NOBLOCK)

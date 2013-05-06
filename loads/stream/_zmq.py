from unittest import TestResult
import zmq.green as zmq
from loads.util import DateTimeJSONEncoder


class ZMQStream(object):
    name = 'zmq'
    options = {'endpoint': ('Socket to send the results to',
                            str, 'tcp://127.0.0.1:5558', True)}

    def __init__(self, args):
        self.context = zmq.Context()
        self._push = self.context.socket(zmq.PUSH)
        self._push.connect(args.get('stream_zmq_endpoint',
                                    'tcp://127.0.0.1:5558'))
        self.encoder = DateTimeJSONEncoder()
        self._result = TestResult()
        self.errors = []
        self.failures = []

    # unittest.TestResult APIS
    def startTest(self, test):
        pass
    stopTest = startTest

    def addFailure(self, test, failure):
        exc_info = self._result._exc_info_to_string(failure, test)
        self.failures.append((test, exc_info))
        self.push({'failure': exc_info})

    def addError(self, test, error):
        exc_info = self._result._exc_info_to_string(error, test)
        self.errors.append((test, exc_info))
        self.push({'error': exc_info})

    def addSuccess(self, test):
        pass

    # ZMQ push
    def push(self, data):
        self._push.send(self.encoder.encode(data), zmq.NOBLOCK)

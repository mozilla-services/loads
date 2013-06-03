from cStringIO import StringIO
import traceback

import zmq.green as zmq

from loads.util import DateTimeJSONEncoder


class ZMQRelay(object):
    """Relays all the method calls to a zmq endpoint"""

    options = {'endpoint': ('Socket to send the calls to',
                            str, 'tcp://127.0.0.1:5558', True)}

    def __init__(self, args):
        self.args = args
        self.context = zmq.Context()
        self._push = self.context.socket(zmq.PUSH)
        self._push.set_hwm(8096 * 4)
        self._push.setsockopt(zmq.LINGER, 1000)
        self._push.connect(args.get('stream_zmq_endpoint',
                                    'tcp://127.0.0.1:5558'))
        self.encoder = DateTimeJSONEncoder()
        self.wid = self.args['worker_id']

    def startTest(self, test, loads_status):
        self.push('startTest',
                  test=str(test),
                  loads_status=loads_status)

    def startTestRun(self):
        self.push('startTestRun')

    def stopTestRun(self):
        self.push('stopTestRun')

    def stopTest(self, test, loads_status):
        self.push('stopTest',
                  test=str(test),
                  loads_status=loads_status)

    def _transform_exc_info(self, exc):
        string = StringIO()
        exc, exc_class, tb = exc
        tb = traceback.print_tb(tb, string)
        return str(exc), str(exc_class), tb

    def addFailure(self, test, exc, loads_status):
        # Because the information to trace the exception is a python object, it
        # may not be JSON-serialisable, so we just pass its string
        # representation.
        self.push('addFailure',
                  test=str(test),
                  exc_info=self._transform_exc_info(exc),
                  loads_status=loads_status)

    def addError(self, test, exc, loads_status):
        self.push('addError',
                  test=str(test),
                  exc_info=self._transform_exc_info(exc),
                  loads_status=loads_status)

    def addSuccess(self, test, loads_status):
        self.push('addSuccess',
                  test=str(test),
                  loads_status=loads_status)

    def add_hit(self, **data):
        self.push('add_hit', **data)

    def socket_open(self, loads_status):
        self.push('socket_open', loads_status=loads_status)

    def socket_close(self, loads_status):
        self.push('socket_close', loads_status)

    def socket_message(self, size, loads_status):
        self.push('socket_message', size=size, loads_status=loads_status)

    def push(self, data_type, **data):
        data.update({'data_type': data_type, 'worker_id': self.wid})
        self._push.send(self.encoder.encode(data), zmq.NOBLOCK)

    def add_observer(self, *args, **kwargs):
        pass  # NOOP

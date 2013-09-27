from cStringIO import StringIO
import traceback
import errno

import zmq.green as zmq

from loads.util import DateTimeJSONEncoder


class ZMQTestResult(object):
    """Relays all the method calls to a zmq endpoint"""

    def __init__(self, args):
        self.args = args
        self.context = args.get('zmq_context', zmq.Context())
        self._init_socket()
        self.encoder = DateTimeJSONEncoder()
        self.agent_id = self.args.get('agent_id')
        self.run_id = self.args.get('run_id')

    def _init_socket(self):
        receive = self.args['zmq_receiver']
        self._push = self.context.socket(zmq.PUSH)
        self._push.set_hwm(8096 * 10)
        self._push.setsockopt(zmq.LINGER, -1)
        self._push.connect(receive)

    def startTest(self, test, loads_status):
        self.push('startTest',
                  test=str(test),
                  loads_status=loads_status)

    def startTestRun(self, agent_id=None):
        self.push('startTestRun')

    def stopTestRun(self, agent_id=None):
        self.push('stopTestRun')

    def stopTest(self, test, loads_status):
        self.push('stopTest',
                  test=str(test),
                  loads_status=loads_status)

    def _transform_exc_info(self, exc):
        string_tb = StringIO()
        exc, exc_class, tb = exc
        traceback.print_tb(tb, file=string_tb)
        string_tb.seek(0)
        return str(exc), str(exc_class), string_tb.read()

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

    def socket_open(self):
        self.push('socket_open')

    def socket_close(self):
        self.push('socket_close')

    def socket_message(self, size):
        self.push('socket_message', size=size)

    def incr_counter(self, test, loads_status, name, agent_id=None):
        self.push(name, test=str(test), loads_status=loads_status,
                  agent_id=str(agent_id))

    def push(self, data_type, **data):
        data.update({'data_type': data_type,
                     'agent_id': self.agent_id,
                     'run_id': self.run_id})
        while True:
            try:
                self._push.send(self.encoder.encode(data), zmq.NOBLOCK)
                return
            except zmq.ZMQError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    continue
                else:
                    raise

    def add_observer(self, *args, **kwargs):
        pass  # NOOP

    def close(self):
        self.context.destroy()

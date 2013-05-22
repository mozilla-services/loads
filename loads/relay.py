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
        self._push.setsockopt(zmq.HWM, 8096 * 4)
        self._push.setsockopt(zmq.SWAP, 200 * 2 ** 10)
        self._push.setsockopt(zmq.LINGER, 1000)
        self._push.connect(args.get('stream_zmq_endpoint',
                                    'tcp://127.0.0.1:5558'))
        self.encoder = DateTimeJSONEncoder()
        self.wid = self.args['worker_id']

    def startTest(self, test, cycle, user, current_cycle):
        self.push('startTest',
                  test=test.__name__,
                  cycle=cycle,
                  user=user,
                  current_cycle=current_cycle)

    def stopTest(self, test, cycle, user, current_cycle):
        self.push('stopTest',
                  test=test.__name__,
                  cycle=cycle,
                  user=user,
                  current_cycle=current_cycle)

    def addFailure(self, test, exc, cycle, user, current_cycle):
        self.push('addFailure',
                  test=test.__name__,
                  exc=exc,
                  cycle=cycle,
                  user=user,
                  current_cycle=current_cycle)

    def addError(self, test, exc, cycle, user, current_cycle):
        self.push('addError',
                  test=test.__name__,
                  exc=exc,
                  cycle=cycle,
                  user=user,
                  current_cycle=current_cycle)

    def addSuccess(self, test, cycle, user, current_cycle):
        self.push('addSuccess',
                  test=test.__name__,
                  cycle=cycle,
                  user=user,
                  current_cycle=current_cycle)

    def add_hit(self, **data):
        self.push('add_hit', **data)

    def socket_open(self):
        self.push('socket_open')

    def socket_message(self, size):
        self.push('socket_message', size=size)

    def push(self, data_type, **data):
        data.update({'data_type': data_type, 'worker_id': self.wid})
        self._push.send(self.encoder.encode(data), zmq.NOBLOCK)

    def add_observer(self, *args, **kwargs):
        pass  # NOOP

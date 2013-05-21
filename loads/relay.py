import functools

import zmq.green as zmq

from loads.util import DateTimeJSONEncoder


class ZMQRelay(object):
    """Relays all the method calls to a zmq endpoint"""

    options = {'endpoint': ('Socket to send the calls to',
                            str, 'tcp://127.0.0.1:5558', True)}

    def __init__(self, args):
        self.context = zmq.Context()
        self._push = self.context.socket(zmq.PUSH)
        self._push.setsockopt(zmq.HWM, 8096 * 4)
        self._push.setsockopt(zmq.SWAP, 200 * 2 ** 10)
        self._push.setsockopt(zmq.LINGER, 1000)
        self._push.connect(args.get('stream_zmq_endpoint',
                                    'tcp://127.0.0.1:5558'))
        self.encoder = DateTimeJSONEncoder()
        self.wid = self.args['worker_id']

    def __getattr__(self, name):
        # Relay all the methods to the self.push method if they are part of the
        # protocol.
        if name in ('startTest', 'stopTest', 'addFailure', 'addError',
                    'addSuccess', 'add_hit'):  # XXX change to camel_case
            return functools.partial(self.push, data_type=name)

    def push(self, data_type, **data):
        data.update({'data_type': data_type, 'worker_id': self.wid})
        self._push.send(self.encoder.encode(data), zmq.NOBLOCK)

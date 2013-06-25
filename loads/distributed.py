import json

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from loads.runner import Runner
from loads.transport.util import DEFAULT_PUBLISHER
from loads.util import logger
from loads.test_result import TestResult
from loads.transport.client import Client


class DistributedRunner(Runner):
    """Test runner distributing the load on a cluster of agents, collecting the
    results via a ZMQ stream.

    The runner need to have agents already up and running. It will send them
    commands trough the ZMQ pipeline and get back their results, which will be
    in turn sent to the local test_result object.
    """
    def __init__(self, args):
        super(DistributedRunner, self).__init__(args)
        self.ended = self.hits = 0
        self.loop = None
        self.test_result = TestResult()

        # socket where the results are published
        self.context = zmq.Context()
        self.pull = self.context.socket(zmq.SUB)
        self.pull.setsockopt(zmq.SUBSCRIBE, '')
        self.pull.set_hwm(8096 * 10)
        self.pull.setsockopt(zmq.LINGER, -1)
        self.pull.connect(self.args.get('zmq_publisher', DEFAULT_PUBLISHER))

        # io loop
        self.loop = ioloop.IOLoop()
        self.zstream = zmqstream.ZMQStream(self.pull, self.loop)
        self.zstream.on_recv(self._recv_result)
        self.outputs = []

        outputs = args.get('output', ['stdout'])

        for output in outputs:
            self.register_output(output)

    def _recv_result(self, msg):
        """When we receive some data from zeromq, send it to the test_result
           for later use."""
        self.loop.add_callback(self._process_result, msg)

    def _process_result(self, msg):

        try:
            data = json.loads(msg[0])
            data_type = data.pop('data_type')

            method = getattr(self.test_result, data_type)
            method(**data)

            if data_type == 'stopTestRun':
                self.loop.stop()
        except Exception:
            self.loop.stop()
            raise

    def _execute(self):
        # calling the clients now
        self.test_result.startTestRun()

        cb = ioloop.PeriodicCallback(self.refresh, 100, self.loop)
        cb.start()
        try:
            client = Client(self.args['broker'])
            logger.debug('Calling the broker...')
            client.run(self.args)
            logger.debug('Waiting for results')
            self.loop.start()
        finally:
            # end..
            cb.stop()
            self.test_result.stopTestRun()
            self.context.destroy()
            self.flush()

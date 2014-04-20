import json

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from loads.runners.local import LocalRunner
from loads.transport.util import DEFAULT_PUBLISHER, DEFAULT_SSH_PUBLISHER
from loads.util import logger, split_endpoint
from loads.results import TestResult, RemoteTestResult
from loads.transport.client import Client


class DistributedRunner(LocalRunner):
    """Test runner distributing the load on a cluster of agents, collecting the
    results via a ZMQ stream.

    The runner need to have agents already up and running. It will send them
    commands trough the ZMQ pipeline and get back their results, which will be
    in turn sent to the local test_result object.
    """

    name = 'distributed'
    options = {}

    def __init__(self, args):
        super(DistributedRunner, self).__init__(args)
        self.ssh = args.get('ssh')
        self.run_id = None
        self._stopped_agents = 0
        self._nb_agents = args.get('agents')

        # socket where the results are published
        self.context = zmq.Context()
        self.sub = self.context.socket(zmq.SUB)
        self.sub.setsockopt(zmq.SUBSCRIBE, '')
        self.sub.set_hwm(8096 * 10)
        self.sub.setsockopt(zmq.LINGER, -1)
        self.zmq_publisher = None
        self.zstream = None

        # io loop
        self.loop = ioloop.IOLoop()

        self.zstream = zmqstream.ZMQStream(self.sub, self.loop)
        self.zstream.on_recv(self._recv_result)

        self.agents = []
        self._client = None
        self.refresh_rate = 100

    @property
    def client(self):
        if self._client is None:
            self._client = Client(self.args['broker'],
                                  ssh=self.args.get('ssh'))
        return self._client

    @property
    def test_result(self):
        if self._test_result is None:
            if self.args.get('attach', False):
                self._test_result = RemoteTestResult(args=self.args)
                self.refresh_rate = 500
            else:
                self._test_result = TestResult(args=self.args)

            # we want to reattach the outputs from Local
            for output in self.outputs:
                self._test_result.add_observer(output)

        return self._test_result

    def _recv_result(self, msg):
        """When we receive some data from zeromq, send it to the test_result
           for later use."""
        self.loop.add_callback(self._process_result, msg)

    def _process_result(self, msg):
        try:
            data = json.loads(msg[0])
            data_type = data.pop('data_type')
            run_id = data.pop('run_id', None)

            if hasattr(self.test_result, data_type):
                method = getattr(self.test_result, data_type)
                method(**data)

            agent_stopped = (data_type == 'batch'
                             and 'stopTestRun' in data['counts'])
            agent_stopped = agent_stopped or data_type == 'stopTestRun'

            if agent_stopped:
                # Make sure all the agents are finished before stopping the
                # loop.
                self._stopped_agents += 1
                if self._stopped_agents == self._nb_agents:
                    self.test_result.sync(self.run_id)
                    self.loop.stop()
            elif data_type == 'run-finished':
                if run_id == self.run_id:
                    self.test_result.sync(self.run_id)
                    self.loop.stop()
        except Exception:
            self.loop.stop()
            raise

    def _attach_publisher(self):
        zmq_publisher = self.args.get('zmq_publisher')

        if zmq_publisher in (None, DEFAULT_PUBLISHER):
            # if this option is not provided by the command line,
            # we ask the broker about it
            res = self.client.ping()
            endpoint = res['endpoints']['publisher']
            if endpoint.startswith('ipc'):
                # IPC - lets hope we're on the same box
                zmq_publisher = endpoint
            elif endpoint.startswith('tcp'):
                # TCP, let's see what IP & port we have
                splitted = split_endpoint(endpoint)
                if splitted['ip'] == '0.0.0.0':
                    # let's use the broker ip
                    broker = self.args['broker']
                    broker_ip = split_endpoint(broker)['ip']
                    zmq_publisher = 'tcp://%s:%d' % (broker_ip,
                                                     splitted['port'])
                else:
                    # let's use the original ip
                    zmq_publisher = endpoint
            else:
                zmq_publisher = DEFAULT_PUBLISHER

        if not self.ssh:
            self.sub.connect(zmq_publisher)
        else:
            if zmq_publisher == DEFAULT_PUBLISHER:
                zmq_publisher = DEFAULT_SSH_PUBLISHER
            from zmq import ssh
            ssh.tunnel_connection(self.sub, zmq_publisher, self.ssh)

        self.zstream = zmqstream.ZMQStream(self.sub, self.loop)
        self.zstream.on_recv(self._recv_result)
        self.zmq_publisher = zmq_publisher

    def _execute(self):
        # calling the clients now
        self.test_result.startTestRun()
        detached = self.args.get('detach')

        if not detached:
            cb = ioloop.PeriodicCallback(self.refresh, self.refresh_rate,
                                         self.loop)
            cb.start()

        try:
            self._attach_publisher()
            logger.debug('Calling the broker...')
            res = self.client.run(self.args)
            self.run_id = res['run_id']
            self.agents = res['agents']

            if not detached:
                logger.debug('Waiting for results')
                self.loop.start()
            else:
                logger.info('Detached. run --attach to reattach')

        finally:
            if not detached:
                # end..
                cb.stop()
                self.test_result.stopTestRun()
                self.context.destroy()
                self.flush()

    def cancel(self):
        self.client.stop_run(self.run_id)

    def attach(self, run_id, started, counts, args):
        self._attach_publisher()
        self.test_result.args = args
        self.test_result.startTestRun(when=started)
        self.test_result.set_counts(counts)
        for output in self.outputs:
            output.args = args

        cb = ioloop.PeriodicCallback(self.refresh, self.refresh_rate,
                                     self.loop)
        cb.start()

        self.run_id = run_id
        try:
            self.loop.start()
        finally:
            # end
            cb.stop()
            self.test_result.stopTestRun()
            self.context.destroy()
            self.flush()

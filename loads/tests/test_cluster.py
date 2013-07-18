import unittest
import logging
import os
import tempfile
import time

from loads.transport import get_cluster, client
from loads.tests.support import hush


logger = logging.getLogger('loads')


class TestCluster(unittest.TestCase):

    def setUp(self):
        self.clusters = []
        self.files = []
        self.old_timeout = client.DEFAULT_TIMEOUT
        self.old_movf = client.DEFAULT_TIMEOUT_MOVF
        self.old_ovf = client.DEFAULT_TIMEOUT_OVF
        client.DEFAULT_TIMEOUT = .5
        client.DEFAULT_TIMEOUT_MOVF = 1.
        client.DEFAULT_TIMEOUT_OVF = 1
        self.overflow = client.DEFAULT_TIMEOUT + .5
        self.moverflow = client.DEFAULT_TIMEOUT_MOVF + .5

    def tearDown(self):
        logger.debug('stopping cluster')
        for cl in self.clusters:
            cl.stop()
        for fl in self.files:
            os.remove(fl)
        logger.debug('cluster stopped')
        client.DEFAULT_TIMEOUT = self.old_timeout
        client.DEFAULT_TIMEOUT_MOVF = self.old_movf
        client.DEFAULT_TIMEOUT_OVF = self.old_ovf

    def _get_file(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        self.files.append(path)
        return path

    def _get_cluster(self, **kw):
        logger.debug('getting cluster')
        front = 'ipc:///tmp/f-tests-cluster'
        back = 'ipc:///tmp/b-tests-cluster'
        hb = 'ipc:///tmp/h-tests-cluster'
        reg = 'ipc:///tmp/r-tests-cluster'

        cl = get_cluster(frontend=front, backend=back, heartbeat=hb,
                         register=reg,
                         numprocesses=1, background=True, debug=False,
                         timeout=client.DEFAULT_TIMEOUT_MOVF, **kw)

        cl.start()
        time.sleep(1.)  # stabilization
        self.clusters.append(cl)
        logger.debug('cluster ready')
        cli = client.Pool(size=3, frontend=front, debug=True,
                          timeout=client.DEFAULT_TIMEOUT,
                          timeout_max_overflow=client.DEFAULT_TIMEOUT_MOVF,
                          timeout_overflows=client.DEFAULT_TIMEOUT_OVF)
        workers = cli.list()
        while len(workers) != 1:
            time.sleep(1.)
            workers = cli.list()

        return cli, cl

    @hush
    def test_success(self):
        client, cluster = self._get_cluster()
        job = {'fqn': 'loads.tests.jobs.SomeTests.test_one'}
        res = client.run(job)
        worker_id = res['workers'][0]
        res = {}
        while res == {}:
            res = client.stop(worker_id)

        self.assertEqual(res['status'].values(), ['terminated'])

        # todo: plug the zmq streamer and test it

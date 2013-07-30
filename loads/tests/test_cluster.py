import unittest
import logging
import os
import tempfile

from loads.tests.support import hush, get_cluster


logger = logging.getLogger('loads')


class TestCluster(unittest.TestCase):

    def setUp(self):
        self.files = []
        self.overflow = 1.
        self.moverflow = 1.5
        self.cluster = self.client = None

    def tearDown(self):
        for fl in self.files:
            os.remove(fl)

        if self.cluster is not None:
            self.cluster.stop()

        if self.client is not None:
            self.client.close()

    def _get_file(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        self.files.append(path)
        return path

    @hush
    def test_success(self):
        self.client, self.cluster = get_cluster(wait=False)
        job = {'fqn': 'loads.tests.jobs.SomeTests.test_one'}
        res = self.client.run(job)
        worker_id = res['workers'][0]
        res = {}
        while res == {}:
            res = self.client.stop(worker_id)

        self.assertEqual(res['status'].values(), ['terminated'])

        # todo: plug the zmq streamer and test it

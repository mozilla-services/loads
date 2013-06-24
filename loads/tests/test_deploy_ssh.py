import unittest2
import time
import os

from loads.deploy.ssh import LoadsHost


class TestLoadsHost(unittest2.TestCase):

    def setUp(self):
        if 'TEST_SSH' not in os.environ:
            return
        self.host = LoadsHost('localhost', 22, 'tarek')
        self.files = []
        self.dirs = []

    def tearDown(self):
        if 'TEST_SSH' not in os.environ:
            return
        self.host.close()

    def test_check_circus(self):
        if 'TEST_SSH' not in os.environ:
            return

        endpoint = 'tcp://0.0.0.0:5555'
        cfg = 'loads.ini'

        self.assertFalse(self.host.check_circus(endpoint))

        self.host.create_env()
        self.host.start_circus(cfg)
        time.sleep(.2)

        self.assertTrue(self.host.check_circus(endpoint))
        self.host.stop_circus()
        time.sleep(.2)

        self.assertFalse(self.host.check_circus(endpoint))

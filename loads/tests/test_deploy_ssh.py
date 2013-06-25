import unittest
import time
import os

from loads.deploy.ssh import LoadsHost


class TestLoadsHost(unittest.TestCase):

    def setUp(self):
        self.host = LoadsHost('0.0.0.0', 2200, 'tarek')
        self.files = []
        self.dirs = []

    def tearDown(self):
        self.host.close()

    @unittest.skipIf('TEST_SSH' not in os.environ, 'no ssh')
    def test_check_circus(self):
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

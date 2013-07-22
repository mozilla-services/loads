import unittest2 as unittest
import time
import os

from loads.deploy.ssh import LoadsHost
from loads.tests.test_deploy_host import start_ssh_server


class TestLoadsHost(unittest.TestCase):

    def setUp(self):
        start_ssh_server()
        self.host = LoadsHost('0.0.0.0', 2200, 'tarek')
        self.files = []
        self.dirs = []

    def tearDown(self):
        self.host.close()

    @unittest.skipIf('TRAVIS' in os.environ, 'Travis')
    def test_check_circus(self):
        endpoint = 'tcp://0.0.0.0:5555'
        cfg = os.path.join('conf', 'loads.ini')
        self.assertFalse(self.host.check_circus(endpoint))

        self.host.create_env()
        self.host.start_circus(cfg)
        time.sleep(.2)

        self.assertTrue(self.host.check_circus(endpoint))
        self.host.stop_circus()
        time.sleep(.2)

        self.assertFalse(self.host.check_circus(endpoint))

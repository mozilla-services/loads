import unittest
import tempfile
import os

from loads.deploy.host import Host


class TestHost(unittest.TestCase):

    def setUp(self):
        self.host = Host('localhost', 22, 'tarek')

    def tearDown(self):
        self.host.close()

    def test_execute_and_put(self):
        stdout, stderr = self.host.execute('ls /tmp')
        files = [f[len('localhost:'):] for f in stdout.split('\n') if f != '']

        # now let's push a file
        fd, temp = tempfile.mkstemp()
        os.close(fd)

        with open(temp, 'w') as f:
            f.write('xxx')

        try:
            self.host.put(temp, temp + '.newname')

            with open(temp + '.newname') as f:
                self.assertEqual(f.read(), 'xxx')
        finally:
            os.remove(temp)
            os.remove(temp + '.newname')

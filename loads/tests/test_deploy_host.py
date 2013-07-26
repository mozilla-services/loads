import unittest2 as unittest
import tempfile
import os
import shutil
import time
import socket

from loads.deploy.host import Host
from loads.tests.support import start_process, stop_process


def start_ssh_server():
    process = start_process('loads.tests.ssh_server')
    tries = 0
    while True:
        try:
            Host('0.0.0.0', 2200, 'tarek', 'xxx')
        except socket.error:
            tries += 1
            if tries >= 10:
                raise
            time.sleep(.1)
        else:
            break

    return process


@unittest.skipIf('TRAVIS' in os.environ, 'Travis')
class TestHost(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ssh = start_ssh_server()
        cls.host = Host('0.0.0.0', 2200, 'tarek', 'xx')
        cls.files = []
        cls.dirs = []

    @classmethod
    def tearDownClass(cls):
        cls.host.close()
        for dir in cls.dirs:
            if os.path.exists(dir):
                shutil.rmtree(dir)

        for file in cls.files:
            if os.path.exists(file):
                os.remove(file)
        stop_process(cls.ssh)

    @classmethod
    def _get_file(cls):
        fd, temp = tempfile.mkstemp()
        os.close(fd)
        cls.files.append(temp)
        return temp

    @classmethod
    def _get_dir(cls):
        dir = tempfile.mkdtemp()
        cls.dirs.append(dir)
        return dir

    def test_execute_and_put(self):
        # now let's push a file
        temp = self._get_file()
        with open(temp, 'w') as f:
            f.write('xxx')

        try:
            self.host.put(temp, temp + '.newname')

            with open(temp + '.newname') as f:
                self.assertEqual(f.read(), 'xxx')
        finally:
            os.remove(temp + '.newname')

    def test_put_dir(self):
        # creating a dir with 3 files
        dir = self._get_dir()
        for i in range(3):
            path = os.path.join(dir, str(i))
            with open(path, 'w') as f:
                f.write(str(i))

        target = dir + '.new'
        self.host.put_dir(dir, target)

        # let's check what we got
        files = os.listdir(target)
        files.sort()
        self.assertEqual(files, ['0', '1', '2'])

    def test_chdir(self):
        tmpdir = self._get_dir()
        self.host.execute('mkdir subdir')
        self.host.chdir('subdir')
        self.host.execute('touch file')
        self.assertTrue(os.path.join(tmpdir, 'subdir', 'file'))

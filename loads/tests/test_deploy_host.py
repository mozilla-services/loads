import unittest2 as unittest
import tempfile
import os
import shutil
import time
import socket

from loads.deploy.host import Host
from loads.tests.support import start_process


_RUNNING = False


def start_ssh_server():
    global _RUNNING
    if _RUNNING:
        return

    start_process('loads.tests.ssh_server')
    tries = 0
    while True:
        try:
            Host('0.0.0.0', 2200, 'tarek')
        except socket.error:
            tries += 1
            if tries >= 5:
                raise
            time.sleep(.2)
        else:
            break

    _RUNNING = True


class TestHost(unittest.TestCase):

    def setUp(self):
        start_ssh_server()
        self.host = Host('0.0.0.0', 2200, 'tarek')
        self.files = []
        self.dirs = []

    def tearDown(self):
        self.host.close()
        for dir in self.dirs:
            if os.path.exists(dir):
                shutil.rmtree(dir)

        for file in self.files:
            if os.path.exists(file):
                os.remove(file)

    def _get_file(self):
        fd, temp = tempfile.mkstemp()
        os.close(fd)
        self.files.append(temp)
        return temp

    def _get_dir(self):
        dir = tempfile.mkdtemp()
        self.dirs.append(dir)
        return dir

    @unittest.skipIf('TRAVIS' in os.environ, 'Travis')
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

    @unittest.skipIf('TRAVIS' in os.environ, 'Travis')
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

    @unittest.skipIf('TRAVIS' in os.environ, 'Travis')
    def test_chdir(self):
        tmpdir = self._get_dir()
        host = Host('localhost', 22, 'tarek', root=tmpdir)
        host.execute('mkdir subdir')
        host.chdir('subdir')
        host.execute('touch file')
        self.assertTrue(os.path.join(tmpdir, 'subdir', 'file'))

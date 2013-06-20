import unittest
import tempfile
import os
import shutil

from loads.deploy.host import Host


class TestHost(unittest.TestCase):

    def setUp(self):
        self.host = Host('localhost', 22, 'tarek')

    def tearDown(self):
        self.host.close()

    def test_execute_and_put(self):
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

    def test_put_dir(self):
        # creating a dir with 3 files
        dir = tempfile.mkdtemp()
        for i in range(3):
            path = os.path.join(dir, str(i))
            with open(path, 'w') as f:
                f.write(str(i))

        try:
            target = dir + '.new'
            self.host.put_dir(dir, target)

            # let's check what we got
            files = os.listdir(target)
            files.sort()
            self.assertEqual(files, ['0', '1', '2'])
        finally:
            shutil.rmtree(dir)
            shutil.rmtree(target)

import time
import os
import gevent
import subprocess
import sys

from loads.case import TestCase


_SERVER = [sys.executable, '%s/echo_server.py' % os.path.dirname(__file__)]


class TestWebSite(TestCase):

    def setUp(self):
        self._server = subprocess.Popen(_SERVER)
        time.sleep(.5)

    def tearDown(self):
        self._server.terminate()
        self._server.wait()

    def test_something(self):
        from gevent.monkey import patch_socket
        patch_socket()
        res = self.session.get('http://localhost:9000')
        self.assertTrue('chatform' in res.content)
        results = []

        def callback(m):
            results.append(m.data)

        ws = self.create_ws('ws://localhost:9000/ws', callback=callback)

        one = 'something' + os.urandom(10).encode('hex')
        two = 'happened' + os.urandom(10).encode('hex')

        ws.send(one)
        ws.send(two)

        start = time.time()
        while one not in results and two not in results:
            gevent.sleep(0)
            if time.time() - start > 1:
                raise AssertionError('Too slow')

    def _test_will_fail(self):
        res = self.session.get('http://localhost:9200')
        self.assertTrue('xFsj' in res.content)

    def _test_will_error(self):
        res = self.session.get('http://localhost:9200')
        raise ValueError(res)

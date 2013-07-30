import time
import os
import gevent
import subprocess
import sys

import requests
import webtest

from loads.case import TestCase
from loads.tests.support import hush, patch_socket, unpatch_socket


_HERE = os.path.dirname(__file__)
_SERVER = [sys.executable,
           os.path.join(_HERE, '..', 'examples', 'echo_server.py')]


class TestWebSite(TestCase):

    server_url = 'http://localhost:9000'

    @classmethod
    def setUpClass(cls):
        cls.old_attrs = patch_socket()
        devnull = open('/dev/null', 'w')
        cls._server = subprocess.Popen(_SERVER, stdout=devnull,
                                       stderr=devnull)
        # wait for the echo server to be started
        tries = 0
        while True:
            try:
                requests.get(cls.server_url)
                break
            except requests.ConnectionError:
                time.sleep(.1)
                tries += 1
                if tries > 20:
                    raise

    @classmethod
    def tearDownClass(cls):
        cls._server.terminate()
        cls._server.wait()
        unpatch_socket(cls.old_attrs)

    @hush
    def test_something(self):
        res = self.app.get('/')
        self.assertTrue('chatform' in res.body)
        results = []

        def callback(m):
            results.append(m.data)

        ws = self.create_ws('ws://localhost:9000/ws',
                            protocols=['chat', 'http-only'],
                            callback=callback)

        one = 'something' + os.urandom(10).encode('hex')
        two = 'happened' + os.urandom(10).encode('hex')

        ws.send(one)
        ws.receive()
        ws.send(two)
        ws.receive()

        start = time.time()
        while one not in results and two not in results:
            gevent.sleep(0)
            if time.time() - start > 1:
                raise AssertionError('Too slow')

    def test_will_fail(self):
        res = self.app.get('/')
        self.assertFalse('xFsj' in res.body)

    def test_webtest_integration(self):
        self.assertRaises(webtest.AppError, self.app.get, '/', status=400)

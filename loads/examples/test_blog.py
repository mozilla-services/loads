import gevent
import random
import os
import time

from loads.case import TestCase


class TestWebSite(TestCase):

    server_url = 'http://blog.ziade.org'

    def test_health(self):
        self.incr_counter('health-check')

    def test_volume(self):
        self.incr_counter('volume-check')

        # eat the CPU a bit, and do a little bit of fd
        for i in range(1000):
            os.urandom(2048)
            i * (i * i * i)

        for i in range(10):
            self.incr_counter('volume-check-%d' % i)
        gevent.sleep(.2)

    def test_hold_health(self):
        self.incr_counter('health-check')
        gevent.sleep(1.)
        raise Exception('BOUH')

    def test_wontdie(self):

        def _spin(*args):
            while True:
                print('WWWWWwwwwwwoooo')

        import signal
        signal.signal(signal.SIGTERM, _spin)
        gevent.sleep(1.)

    def test_public(self):
        self.session.get('http://google.com')

    def test_gonuts(self):
        root = 'http://ec2-54-244-173-6.us-west-2.compute.amazonaws.com:8282'
        res = self.session.get(root + '/%s' %
                               random.choice(['here', 'there', 'foo']))
        self.assertTrue('nuts' in res.content.lower())

    def test_es(self):
        self.incr_counter('es')
        self.session.get('http://localhost:9200')

    def test_hold_ws(self):
        results = []

        def callback(m):
            self.incr_counter('socket-callback')
            results.append(m.data)

        self.incr_counter('socket-created')
        ws = self.create_ws('ws://localhost:9000/ws',
                            callback=callback)

        start = time.time()

        while time.time() - start < 240:
            gevent.sleep(1)
            ws.send('x')
            gevent.sleep(2)
            ws.receive()
            gevent.sleep(7)

        ws.close()

    def test_from_doc(self):
        results = []

        def callback(m):
            results.append(m.data)

        ws = self.create_ws('ws://localhost:9000/ws',
                            protocols=['chat', 'http-only'],
                            callback=callback)
        ws.send('something')
        ws.receive()
        ws.send('happened')
        ws.receive()

        while len(results) < 2:
            time.sleep(.1)

        self.assertEqual(results, ['something', 'happened'])

    def test_something(self):
        res = self.session.get('http://localhost:9000')
        self.assertTrue('chatform' in res.content)
        results = []

        def callback(m):
            self.incr_counter('socket-callback')
            results.append(m.data)

        self.incr_counter('socket-created')
        ws = self.create_ws('ws://localhost:9000/ws',
                            protocols=['chat', 'http-only'],
                            callback=callback)

        one = 'something' + os.urandom(10).encode('hex')
        two = 'happened' + os.urandom(10).encode('hex')

        ws.send(one)
        ws.receive()
        ws.send(two)
        ws.receive()
        self.incr_counter('socket-sent')

        start = time.time()
        while one not in results and two not in results:
            gevent.sleep(0)
            if time.time() - start > 1:
                raise AssertionError('Too slow')

    def _test_will_fail(self):
        res = self.session.get('http://localhost:9200')
        self.assertTrue('xFsj' in res.content)

    def test_will_error(self):
        raise ValueError("boom")

    def test_concurrency(self):
        self.incr_counter('beau')
        user = 'user%s' % random.randint(1, 200)
        self.session.auth = (user, 'X' * 10)
        self.app.server_url = 'http://localhost:9000'
        res = self.app.get('/auth')
        # don't use assertIn so this works with 2.6
        self.assertTrue(user in res.body)
        res = self.app.get('/auth')
        self.assertTrue(user in res.body)
        self.incr_counter('lavabo')

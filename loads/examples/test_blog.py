import time
import os

from loads import TestCase


class TestWebSite(TestCase):

    def test_something(self):
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
            time.sleep(.1)
            if time.time() - start > 1:
                raise AssertionError('Too slow')

    def _test_will_fail(self):
        res = self.session.get('http://localhost:9200')
        self.assertTrue('xFsj' in res.content)

    def _test_will_error(self):
        res = self.session.get('http://localhost:9200')
        raise ValueError(res)

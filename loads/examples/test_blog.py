import time

from loads import TestCase


class TestWebSite(TestCase):

    def test_something(self):
        res = self.session.get('http://localhost:9000')
        self.assertTrue('chatform' in res.content)
        results = []

        def callback(m):
            results.append(m.data)

        ws = self.create_ws('ws://localhost:9000/ws',
                            callback=callback)
        ws.send('something')
        ws.send('happened')

        while len(results) < 2:
            time.sleep(.1)
        ws.close()

        self.assertEqual(results, ['something', 'happened'])

    def _test_will_fail(self):
        res = self.session.get('http://localhost:9200')
        self.assertTrue('xFsj' in res.content)

    def _test_will_error(self):
        res = self.session.get('http://localhost:9200')
        raise ValueError(res)

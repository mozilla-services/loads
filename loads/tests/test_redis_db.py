import unittest2
import time

from zmq.green.eventloop import ioloop
try:
    from loads.db._redis import RedisDB
    import redis
    redis.StrictRedis().ping()
    NO_TEST = False
except Exception:
    NO_TEST = True

from loads.tests.test_python_db import ONE_RUN
from loads.util import json


_KEYS = ['errors:1', 'errors:2', 'data:1', 'data:2', 'counters:1',
         'counters:2', 'bcounters:1',
         'bcounters:2', 'metadata:1', 'metadata:2',
         'urls:1', 'urls:2']


for type_ in ('addSuccess', 'stopTestRun', 'stopTest',
              'startTest', 'startTestRun', 'add_hit'):
    _KEYS.append('count:1:%s' % type_)
    _KEYS.append('count:2:%s' % type_)


@unittest2.skipIf(NO_TEST, 'No redis')
class TestRedisDB(unittest2.TestCase):

    def setUp(self):
        self.loop = ioloop.IOLoop()
        self.db = RedisDB(self.loop)
        self._redis = redis.StrictRedis()

    def tearDown(self):
        self.loop.close()
        for md5 in self._redis.smembers('bcounters:1'):
            self._redis.delete('bcount:1:%s' % md5)

        for md5 in self._redis.smembers('bcounters:2'):
            self._redis.delete('bcount:1:%s' % md5)

        for url in self._redis.smembers('urls:2'):
            self._redis.delete('url:2:%s' % url)

        for url in self._redis.smembers('urls:1'):
            self._redis.delete('url:1:%s' % url)

        for key in _KEYS:
            self._redis.delete(key)

        self.db.flush()
        self.db.close()

    def test_brokerdb(self):
        self.assertEqual(list(self.db.get_data('swwqqsw')), [])
        self.assertTrue(self.db.ping())

        def add_data():
            for line in ONE_RUN:
                data = dict(line)
                data['run_id'] = '1'
                self.db.add(data)
                data['run_id'] = '2'
                self.db.add(data)

        self.loop.add_callback(add_data)
        self.loop.add_callback(add_data)

        self.loop.add_timeout(time.time() + .5, self.loop.stop)
        self.loop.start()

        # let's check if we got the data in the file
        data = [json.loads(self._redis.lindex('data:1', i))
                for i in range(self._redis.llen('data:1'))]
        data.sort()

        data2 = [json.loads(self._redis.lindex('data:2', i))
                 for i in range(self._redis.llen('data:2'))]
        data2.sort()

        self.assertEqual(len(data), 14)
        self.assertEqual(len(data2), 14)
        counts = self.db.get_counts('1')

        for type_ in ('addSuccess', 'stopTestRun', 'stopTest',
                      'startTest', 'startTestRun', 'add_hit'):
            self.assertEqual(dict(counts)[type_], 2)

        # we got 12 lines, let's try batching
        batch = list(self.db.get_data('1', size=2))
        self.assertEqual(len(batch), 2)

        batch = list(self.db.get_data('1', start=2))
        self.assertEqual(len(batch), 12)

        batch = list(self.db.get_data('1', start=2, size=5))
        self.assertEqual(len(batch), 5)

        data3 = list(self.db.get_data('1'))
        data3.sort()
        self.assertEqual(data3, data)

        # filtered
        data3 = list(self.db.get_data('1', data_type='add_hit'))
        self.assertEqual(len(data3), 2)

        # group by
        res = list(self.db.get_data('1', groupby=True))
        self.assertEqual(len(res), 7)
        self.assertEqual(res[0]['count'], 2)

        res = list(self.db.get_data('1', data_type='add_hit', groupby=True))
        self.assertEqual(res[0]['count'], 2)
        self.assertTrue('1' in self.db.get_runs())
        self.assertTrue('2' in self.db.get_runs())

        # len(data) < asked ize
        batch = list(self.db.get_data('1', start=2, size=5000))
        self.assertEqual(len(batch), 12)

    def test_metadata(self):
        self.assertEqual(self.db.get_metadata('1'), {})
        self.db.save_metadata('1', {'hey': 'ho'})
        self.assertEqual(self.db.get_metadata('1'), {'hey': 'ho'})

        self.db.update_metadata('1', one=2)
        meta = self.db.get_metadata('1').items()
        meta.sort()
        self.assertEqual(meta, [('hey', 'ho'), ('one', 2)])

    def test_get_urls(self):
        def add_data():
            for line in ONE_RUN:
                data = dict(line)
                data['run_id'] = '1'
                self.db.add(data)
                data['run_id'] = '2'
                self.db.add(data)

        self.loop.add_callback(add_data)
        self.loop.add_callback(add_data)
        self.loop.add_timeout(time.time() + .5, self.loop.stop)
        self.loop.start()

        urls = self.db.get_urls('1')
        self.assertEqual(urls, {'http://127.0.0.1:9200/': 2})

    def test_get_errors(self):
        def add_data():
            for line in ONE_RUN:
                data = dict(line)
                data['run_id'] = '1'
                self.db.add(data)
                data['run_id'] = '2'
                self.db.add(data)

        self.loop.add_callback(add_data)
        self.loop.add_callback(add_data)
        self.loop.add_timeout(time.time() + .5, self.loop.stop)
        self.loop.start()

        self.assertTrue(self.db.ping())

        errors = list(self.db.get_errors('2'))
        self.assertEqual(len(errors), 2, errors)

        errors = list(self.db.get_errors('1'))
        self.assertEqual(len(errors), 2, errors)

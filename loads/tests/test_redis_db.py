import unittest2
import time
import json

from zmq.green.eventloop import ioloop
try:
    from loads.db._redis import RedisDB
    import redis
    redis.StrictRedis().ping()
    NO_TEST = False
except Exception:
    NO_TEST = True

from loads.tests.test_python_db import ONE_RUN


_KEYS = ['data:1', 'data:2', 'counters:1', 'counters:2', 'bcounters:1',
         'bcounters:2']


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

        for key in _KEYS:
            self._redis.delete(key)

    def test_brokerdb(self):
        self.assertEqual(list(self.db.get_data('swwqqsw')), [])

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

        self.assertEqual(len(data), 12)
        self.assertEqual(len(data2), 12)
        counts = self.db.get_counts('1')

        for type_ in ('addSuccess', 'stopTestRun', 'stopTest',
                      'startTest', 'startTestRun', 'add_hit'):
            self.assertEqual(dict(counts)[type_], 2)

        data3 = list(self.db.get_data('1'))
        data3.sort()
        self.assertEqual(data3, data)

        # filtered
        data3 = list(self.db.get_data('1', data_type='add_hit'))
        self.assertEqual(len(data3), 2)

        # group by
        res = list(self.db.get_data('1', groupby=True))
        self.assertEqual(len(res), 6)
        self.assertEqual(res[0]['count'], 2)

        res = list(self.db.get_data('1', data_type='add_hit', groupby=True))
        self.assertEqual(res[0]['count'], 2)

        self.assertEqual(self.db.get_runs(), set(['1', '2']))

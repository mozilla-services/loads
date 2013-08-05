try:
    import redis
except ImportError:
    raise ImportError("You need to install http://pypi.python.org/pypi/redis")

from loads.db import BaseDB
from json import dumps, loads


class RedisDB(BaseDB):
    name = 'redis'
    options = {'host': ('localhost', 'Redis host', str),
               'port': (6379, 'Redis port', int)}

    def _initialize(self):
        self.host = self.params['host']
        self.port = self.params['port']
        self._redis = redis.StrictRedis(host=self.host, port=self.port,
                                        db=0)

    #
    # APIs
    #
    def save_metadata(self, run_id, metadata):
        key = 'metadata:%s' % run_id
        self._redis.set(key, loads(metadata))

    def get_metadata(self, run_id):
        key = 'metadata:%s' % run_id
        return loads(self._redis.get(key))

    def add(self, data):
        run_id = data.get('run_id', 'unknown')
        data_type = data.get('data_type', 'unknown')
        size = data.get('size', 1)

        pipeline = self._redis.pipeline()

        counter = 'count:%s:%s' % (run_id, data_type)
        counters = 'counters:%s' % run_id
        if not self._redis.sismember(counters, counter):
            pipeline.sadd(counters, counter)

        pipeline.incrby('count:%s:%s' % (run_id, data_type), size)
        pipeline.lpush('data:%s' % run_id, dumps(data))
        pipeline.execute()

    def flush(self):
        pass

    def close(self):
        pass

    def get_counts(self, run_id):
        counts = {}
        counters = 'counters:%s' % run_id
        for member in self._redis.smembers(counters):
            name = member.split(':')[-1]
            counts[name] = int(self._redis.get(member))
        return counts

    def get_data(self, run_id):
        key = 'data:%s' % run_id
        len = self._redis.llen(key)
        if len == 0:
            raise StopIteration()
        for index in range(len):
            yield loads(self._redis.lindex(key, index))

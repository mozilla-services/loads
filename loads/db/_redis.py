try:
    import redis
except ImportError:
    raise ImportError("You need to install http://pypi.python.org/pypi/redis")

import hashlib
from json import dumps, loads

from loads.db import BaseDB


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
        self._redis.set(key, dumps(metadata))

    def get_metadata(self, run_id):
        key = 'metadata:%s' % run_id
        metadata = self._redis.get(key)
        if metadata is None:
            return {}
        return loads(metadata)

    def add(self, data):
        if 'run_id' not in data:
            data['run_id'] = 'unknown'
        run_id = data['run_id']

        if 'data_type' not in data:
            data['data_type'] = 'unknown'
        data_type = data['data_type']

        if 'size' not in data:
            data['size'] = 1
        size = data['size']

        pipeline = self._redis.pipeline()
        pipeline.sadd('runs', run_id)
        counter = 'count:%s:%s' % (run_id, data_type)
        counters = 'counters:%s' % run_id
        if not self._redis.sismember(counters, counter):
            pipeline.sadd(counters, counter)

        dumped = dumps(data, sort_keys=True)

        pipeline.incrby('count:%s:%s' % (run_id, data_type), size)
        pipeline.lpush('data:%s' % run_id, dumped)

        # adding group by
        md5 = hashlib.md5(dumped).hexdigest()
        pipeline.incrby('bcount:%s:%s' % (run_id, md5), size)
        pipeline.set('bvalue:%s:%s' % (run_id, md5), dumped)
        bcounters = 'bcounters:%s' % run_id
        if not self._redis.sismember(bcounters, md5):
            pipeline.sadd(bcounters, md5)

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

    def get_runs(self):
        return self._redis.smembers('runs')

    def get_data(self, run_id, data_type=None, groupby=False):
        key = 'data:%s' % run_id
        len = self._redis.llen(key)
        if len == 0:
            raise StopIteration()
        if not groupby:
            for index in range(len):
                data = loads(self._redis.lindex(key, index))
                if data_type is None or data_type == data.get('data_type'):
                    yield data
        else:
            bcounters = 'bcounters:%s' % run_id
            for hash in self._redis.smembers(bcounters):
                data = loads(self._redis.get('bvalue:%s:%s' % (run_id, hash)))
                filtered = (data_type is not None and
                            data_type != data.get('data_type'))
                if filtered:
                    continue

                counter = self._redis.get('bcount:%s:%s' % (run_id, hash))
                data['count'] = int(counter)
                yield data

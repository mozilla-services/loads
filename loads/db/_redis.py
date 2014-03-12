try:
    import redis
except ImportError:
    raise ImportError("You need to install http://pypi.python.org/pypi/redis")

import hashlib

from loads.db import BaseDB
from loads.util import json


class RedisDB(BaseDB):
    name = 'redis'
    options = {'host': ('localhost', 'Redis host', str),
               'port': (6379, 'Redis port', int)}

    def _initialize(self):
        self.host = self.params['host']
        self.port = self.params['port']
        self._redis = redis.StrictRedis(host=self.host, port=self.port,
                                        db=0)

    def ping(self):
        try:
            self._redis.ping()
            return True
        except redis.ConnectionError:
            return False

    #
    # APIs
    #
    def save_metadata(self, run_id, metadata):
        key = 'metadata:%s' % run_id
        self._redis.set(key, json.dumps(metadata))

    def update_metadata(self, run_id, **metadata):
        existing = self.get_metadata(run_id)
        existing.update(metadata)
        self.save_metadata(run_id, existing)

    def get_metadata(self, run_id):
        key = 'metadata:%s' % run_id
        metadata = self._redis.get(key)
        if metadata is None:
            return {}
        return json.loads(metadata)

    def add(self, data):
        run_id = data['run_id']
        data_type = data['data_type'] = data.get('data_type', 'unknown')
        size = data.get('size', 1)

        pipeline = self._redis.pipeline()
        pipeline.sadd('runs', run_id)

        # adding counts
        counter = 'count:%s:%s' % (run_id, data_type)
        counters = 'counters:%s' % run_id
        if not self._redis.sismember(counters, counter):
            pipeline.sadd(counters, counter)

        pipeline.incrby('count:%s:%s' % (run_id, data_type), size)

        # adding urls
        if 'url' in data:
            url = data['url']
            urls = 'urls:%s' % run_id
            if not self._redis.sismember(urls, url):
                pipeline.sadd(urls, url)
            pipeline.incrby('url:%s:%s' % (run_id, url), 1)

        # adding data
        dumped = json.dumps(data)
        pipeline.lpush('data:%s' % run_id, dumped)

        # adding errors
        if data_type == 'addError':
            pipeline.lpush('errors:%s' % run_id, dumped)

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

    def get_urls(self, run_id):
        urls = {}
        for url in self._redis.smembers('urls:%s' % run_id):
            urls[url] = int(self._redis.get('url:%s:%s' % (run_id, url)))

        return urls

    def get_counts(self, run_id):
        counts = {}
        counters = 'counters:%s' % run_id
        for member in self._redis.smembers(counters):
            name = member.split(':')[-1]
            counts[name] = int(self._redis.get(member))
        return counts

    def get_runs(self):
        return self._redis.smembers('runs')

    def get_errors(self, run_id, start=None, size=None):
        key = 'errors:%s' % run_id
        len = self._redis.llen(key)
        if len == 0:
            raise StopIteration()

        if start is None:
            start = 0

        if size is None:
            end = len
        else:
            end = start + size
            if end > len:
                end = len

        for index in range(start, end):
            yield json.loads(self._redis.lindex(key, index))

    def get_data(self, run_id, data_type=None, groupby=False, start=None,
                 size=None):
        key = 'data:%s' % run_id
        len = self._redis.llen(key)
        if len == 0:
            raise StopIteration()

        if not groupby:
            if start is None:
                start = 0

            if size is None:
                end = len
            else:
                end = start + size
                if end > len:
                    end = len

            for index in range(start, end):
                data = json.loads(self._redis.lindex(key, index))
                if data_type is None or data_type == data.get('data_type'):
                    yield data
        else:
            # XXX not sure how to batch this yet
            if start is not None or size is not None:
                raise NotImplementedError()

            bcounters = 'bcounters:%s' % run_id
            for hash in self._redis.smembers(bcounters):
                data = json.loads(self._redis.get('bvalue:%s:%s' %
                                  (run_id, hash)))
                filtered = (data_type is not None and
                            data_type != data.get('data_type'))
                if filtered:
                    continue

                counter = self._redis.get('bcount:%s:%s' % (run_id, hash))
                data['count'] = int(counter)
                yield data

    def prepare_run(self):
        pass

    def is_summarized(self, run_id):
        return False

    def summarize_run(self, run_id):
        pass

    def delete_run(self, run_id):
        pass

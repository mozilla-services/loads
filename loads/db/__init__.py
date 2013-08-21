from loads.util import logger


class BaseDB(object):

    name = ''
    options = {}

    def __init__(self, loop, **kw):
        if self.name == '':
            raise ValueError('You need to set a name')

        self.loop = loop
        self.params = {}
        for key, (default, help, type) in self.options.items():
            self.params[key] = type(kw.get(key, default))

        self._initialize()

    def _initialize(self):
        raise NotImplementedError()

    #
    # APIs
    #
    def save_metadata(self, run_id, metadata):
        raise NotImplementedError()

    def get_metadata(self, run_id):
        raise NotImplementedError()

    def add(self, data):
        raise NotImplementedError()

    def flush(self):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()

    def get_counts(self, run_id):
        raise NotImplementedError()

    def get_data(self, run_id):
        raise NotImplementedError()

    def get_urls(self, run_id):
        raise NotImplementedError()


def get_database(name='python', loop=None, **options):
    if name == 'python':
        from loads.db._python import BrokerDB
        klass = BrokerDB
    elif name == 'redis':
        from loads.db._redis import RedisDB
        klass = RedisDB
    else:
        raise NotImplementedError(name)

    db = klass(loop, **options)
    logger.info('Created a %r database connection' % name)
    return db


def get_backends():
    backends = []

    def _options(backend):
        return[(name, default, help, type_)
               for name, (default, help, type_)
               in backend.options.items()]

    # pure python
    from loads.db._python import BrokerDB
    backends.append((BrokerDB.name, _options(BrokerDB)))

    try:
        from loads.db._redis import RedisDB
    except ImportError:
        return backends

    backends.append((RedisDB.name, _options(RedisDB)))
    return backends

from loads.util import logger


class BaseDB(object):

    name = ''
    options = {}

    def __init__(self, loop, **kw):
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


def get_database(name='python', loop=None, **options):
    if name == 'python':
        from loads.db._python import BrokerDB
        db = BrokerDB(loop, **options)
        logger.info('Created a %r database' % name)
        return db

    raise NotImplementedError(name)


def get_backends():
    from loads.db._python import BrokerDB
    options = [(name, default, help, type_)
               for name, (default, help, type_)
               in BrokerDB.options.items()]
    return [(BrokerDB.name, options)]

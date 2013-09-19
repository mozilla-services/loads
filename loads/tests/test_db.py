import unittest2
from loads.db import get_backends, get_database, BaseDB
try:
    import redis
    redis.StrictRedis().ping()
    NO_REDIS = False
except Exception:
    NO_REDIS = True


class TestDB(unittest2.TestCase):

    def test_get_backends(self):
        backends = get_backends()
        if NO_REDIS:
            self.assertEqual(len(backends), 1)
        else:
            self.assertEqual(len(backends), 2)

    def test_get_database(self):
        db = get_database('python')
        self.assertTrue(db.ping())

        if not NO_REDIS:
            db = get_database('redis')
            self.assertTrue(db.ping())

        self.assertRaises(NotImplementedError, get_database, 'cobol')

    def test_basedb(self):
        self.assertRaises(ValueError, BaseDB, None)

        class MyDB(BaseDB):
            name = 'my'

        self.assertRaises(NotImplementedError, MyDB, None)

        class MyDB2(BaseDB):
            name = 'my'

            def _initialize(self):
                pass

        db2 = MyDB2(None)
        self.assertRaises(NotImplementedError, db2.save_metadata, None, None)
        self.assertRaises(NotImplementedError, db2.get_metadata, None)
        self.assertRaises(NotImplementedError, db2.add, None)
        self.assertRaises(NotImplementedError, db2.flush)
        self.assertRaises(NotImplementedError, db2.close)
        self.assertRaises(NotImplementedError, db2.get_counts, None)
        self.assertRaises(NotImplementedError, db2.get_data, None)
        self.assertRaises(NotImplementedError, db2.get_urls, None)
        self.assertRaises(NotImplementedError, db2.flush)

import unittest2
import time
import os
import shutil
import tempfile

from zmq.green.eventloop import ioloop
from loads.db._python import BrokerDB, read_zfile


_RUN_ID = '8b91dee8-0aec-4bb9-b0a0-87269a9c2874'
_AGENT_ID = 1727

ONE_RUN = [
    {'agent_id': _AGENT_ID, 'data_type': 'startTestRun', 'run_id': _RUN_ID},

    {'agent_id': _AGENT_ID, 'data_type': 'startTest', 'run_id': _RUN_ID,
     'test': 'test_es (loads.examples.test_blog.TestWebSite)',
     'loads_status': [1, 1, 1, 0]},

    {'status': 200, 'loads_status': [1, 1, 1, 0], 'data_type': 'add_hit',
     'run_id': _RUN_ID, 'started': '2013-06-26T10:11:38.838224',
     'elapsed': 0.008656, 'url': 'http://127.0.0.1:9200/',
     'agent_id': _AGENT_ID, u'method': u'GET'},

    {'test': 'test_es (loads.examples.test_blog.TestWebSite)',
     'agent_id': _AGENT_ID, 'loads_status': [1, 1, 1, 0],
     'data_type': 'addSuccess', 'run_id': _RUN_ID},

    {'test': 'test_es (loads.examples.test_blog.TestWebSite)',
     'agent_id': _AGENT_ID, 'loads_status': [1, 1, 1, 0],
     'data_type': 'addError', 'run_id': _RUN_ID},

    {'test': 'test_es (loads.examples.test_blog.TestWebSite)',
     'agent_id': _AGENT_ID, 'loads_status': [1, 1, 1, 0],
     'data_type': 'stopTest', 'run_id': _RUN_ID},

    {'agent_id': _AGENT_ID, 'data_type': 'stopTestRun',
     'run_id': _RUN_ID}]


class TestBrokerDB(unittest2.TestCase):

    def setUp(self):
        self.loop = ioloop.IOLoop()
        self.tmp = tempfile.mkdtemp()
        dboptions = {'directory': self.tmp}
        self.db = BrokerDB(self.loop, db='python',
                           dboptions=dboptions)

    def tearDown(self):
        shutil.rmtree(self.db.directory)
        self.db.close()
        self.loop.close()

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
        self.loop.add_timeout(time.time() + 2.1, self.loop.stop)
        self.loop.start()

        # let's check if we got the data in the file
        db = os.path.join(self.db.directory, '1-db.json')
        data = [record for record, line in read_zfile(db)]
        data.sort()

        db = os.path.join(self.db.directory, '2-db.json')
        data2 = [record for record, line in read_zfile(db)]
        data2.sort()

        self.assertEqual(len(data), 14)
        self.assertEqual(len(data2), 14)
        counts = self.db.get_counts('1')

        for type_ in ('addSuccess', 'stopTestRun', 'stopTest',
                      'startTest', 'startTestRun', 'add_hit'):
            self.assertEqual(counts[type_], 2)

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

        self.assertTrue(self.db.ping())
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

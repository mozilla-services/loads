import unittest2
import time
import os
import shutil
import tempfile
import json

from zmq.green.eventloop import ioloop
from loads.db._python import BrokerDB, read_zfile, get_dir_size


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
                           **dboptions)

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

        data = [self.db._uncompress_headers('1', line) for line in data]
        data.sort()

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

    def test_compression(self):
        headers_f = os.path.join(self.db.directory, 'run-id-headers.json')
        headers = {"1": 'one', "2": 'two'}

        with open(headers_f, 'w') as f:
            f.write(json.dumps(headers))

        data = {'one': 'ok', 'two': 3, 'three': 'blah'}
        self.db._update_headers('run-id')

        self.db.add({'run_id': 'run-id', 'one': 'ok', 'two': 3,
                     'three': 'blah'})

        result = self.db._compress_headers('run-id', data)
        result = result.items()
        result.sort()
        self.assertEqual(result, [(1, 'ok'), (2, 3), (3, 'blah')])
        self.db.flush()

        with open(headers_f) as f:
            new_headers = json.loads(f.read())

        wanted = [(1, u'one'), (2, u'two'), (3, u'three'), (4, u'run_id')]
        new_headers = [(int(key), value) for key, value in new_headers.items()]
        new_headers.sort()
        self.assertEquals(new_headers, wanted)

    @unittest2.skipIf('TRAVIS' in os.environ, '')
    def test_max_size(self):
        # adding some data for run_1 and run_2
        self.db.prepare_run()

        for run in ('run_1', 'run_2', 'run_3'):
            for i in range(1000):
                self.db.add({'run_id': run, 'one': 'ok', 'two': 3,
                             'three': 'blah'})
            # flushing
            self.db.flush()
            time.sleep(.1)

        self.assertEqual(self.db.get_runs(), ['run_1', 'run_2', 'run_3'])

        # setting the max size to current size
        self.db.max_size = get_dir_size(self.tmp)
        self.db.prepare_run()

        # adding data for run_4
        for i in range(1000):
            self.db.add({'run_id': 'run_4', 'one': 'ok', 'two': 3,
                         'three': 'blah'})

        # run-1 should have been wiped...
        self.db.flush()
        self.assertEqual(self.db.get_runs(), ['run_2', 'run_3', 'run_4'])

    def test_reload(self):
        self.assertEqual(self.db.get_metadata('1'), {})
        self.db.save_metadata('1', {'hey': 'ho'})
        self.assertEqual(self.db.get_metadata('1'), {'hey': 'ho'})
        self.db.update_metadata('1', one=2)
        meta = self.db.get_metadata('1').items()
        meta.sort()
        self.assertEqual(meta, [('hey', 'ho'), ('one', 2)])
        self.db.flush()

        # make sure we don't lose existing data when
        # the db client is started and writes before reads
        dboptions = {'directory': self.tmp}
        db2 = BrokerDB(self.loop, db='python', **dboptions)

        # this used to overwrite any existing data
        db2.update_metadata('1', has_data=1)
        meta = db2.get_metadata('1').items()
        meta.sort()
        wanted = [(u'has_data', 1), (u'hey', u'ho'), (u'one', 2)]
        self.assertEqual(meta, wanted)

import unittest
import time
import os
import shutil
import json
import tempfile

from zmq.green.eventloop import ioloop
from loads.db.brokerdb import BrokerDB


_RUN_ID = '8b91dee8-0aec-4bb9-b0a0-87269a9c2874'
_WID = 1727

_ONE_RUN = [
    {'worker_id': _WID, 'data_type': 'startTestRun', 'run_id': _RUN_ID},

    {'worker_id': _WID, 'data_type': 'startTest', 'run_id': _RUN_ID,
     'test': 'test_es (loads.examples.test_blog.TestWebSite)',
     'loads_status': [1, 1, 1, 0]},

    {'status': 200, 'loads_status': [1, 1, 1, 0], 'data_type': 'add_hit',
     'run_id': _RUN_ID, 'started': '2013-06-26T10:11:38.838224',
     'elapsed': 0.008656, 'url': 'http://127.0.0.1:9200/',
     'worker_id': _WID, u'method': u'GET'},

    {'test': 'test_es (loads.examples.test_blog.TestWebSite)',
     'worker_id': _WID, 'loads_status': [1, 1, 1, 0],
     'data_type': 'addSuccess', 'run_id': _RUN_ID},

    {'test': 'test_es (loads.examples.test_blog.TestWebSite)',
     'worker_id': _WID, 'loads_status': [1, 1, 1, 0],
     'data_type': 'stopTest', 'run_id': _RUN_ID},

    {'worker_id': _WID, 'data_type': 'stopTestRun',
     'run_id': _RUN_ID}]


class TestBrokerDB(unittest.TestCase):

    def setUp(self):
        self.loop = ioloop.IOLoop()
        self.tmp = tempfile.mkdtemp()
        self.db = BrokerDB(self.loop, self.tmp)

    def tearDown(self):
        shutil.rmtree(self.db.directory)
        self.db.close()
        self.loop.close()

    def test_brokerdb(self):
        self.assertEqual(list(self.db.get_data('swwqqsw')), [])

        def add_data():
            for line in _ONE_RUN:
                data = dict(line)
                data['run_id'] = '1'
                self.db.add(data)
                data['run_id'] = '2'
                self.db.add(data)

        self.loop.add_callback(add_data)
        self.loop.add_timeout(time.time() + .5, self.loop.stop)
        self.loop.start()

        # let's check if we got the data in the file
        with open(os.path.join(self.db.directory, '1')) as f:
            data = [json.loads(line) for line in f]
        data.sort()

        with open(os.path.join(self.db.directory, '2')) as f:
            data2 = [json.loads(line) for line in f]

        self.assertEqual(len(data), 6)
        self.assertEqual(len(data2), 6)
        counts = self.db.get_counts('1')

        for type_ in ('addSuccess', 'stopTestRun', 'stopTest',
                      'startTest', 'startTestRun', 'add_hit'):
            self.assertEqual(dict(counts)[type_], 1)

        data3 = list(self.db.get_data('1'))
        data3.sort()
        self.assertEqual(data3, data)

import unittest2
import time
import os
import shutil
import json
import tempfile

from zmq.green.eventloop import ioloop
from loads.db._python import BrokerDB


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
        self.loop.add_timeout(time.time() + .5, self.loop.stop)
        self.loop.start()

        # let's check if we got the data in the file
        with open(os.path.join(self.db.directory, '1-db.json')) as f:
            data = [json.loads(line) for line in f]
        data.sort()

        with open(os.path.join(self.db.directory, '2-db.json')) as f:
            data2 = [json.loads(line) for line in f]

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

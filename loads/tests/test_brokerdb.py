import unittest
import time
import os
import shutil

from zmq.green.eventloop import ioloop
from loads.db.brokerdb import BrokerDB


class TestBrokerDB(unittest.TestCase):

    def setUp(self):
        self.loop = ioloop.IOLoop()
        self.db = BrokerDB(self.loop)

    def tearDown(self):
        shutil.rmtree(self.db.directory)
        self.db.close()
        self.loop.close()

    def test_brokerdb(self):

        def add_data():
            data = {'run_id': '1', 'data': 'data'}
            data2 = {'run_id': '2', 'data': 'data'}

            for i in range(100):
                self.db.add(data)
                self.db.add(data2)

        self.loop.add_callback(add_data)
        self.loop.add_timeout(time.time() + .5, self.loop.stop)
        self.loop.start()

        # let's check if we got the data in the file
        with open(os.path.join(self.db.directory, '1')) as f:
            data = f.read().split('\n')

        with open(os.path.join(self.db.directory, '2')) as f:
            data2 = f.read().split('\n')

        self.assertEqual(len(data), 100)
        self.assertEqual(len(data2), 100)

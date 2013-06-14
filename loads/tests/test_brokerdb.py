import unittest
import time

from zmq.green.eventloop import ioloop
from loads.transport.brokerdb import BrokerDB


class TestBrokerDB(unittest.TestCase):

    def test_brokerdb(self):
        loop = ioloop.IOLoop()
        db = BrokerDB(loop)

        def add_data():
            for i in range(100):
                db.add(str(i))

        loop.add_callback(add_data)
        loop.add_timeout(time.time() + .5, loop.stop)
        loop.start()
        db.close()

        # let's check if we got the data in the file
        with open(db.path) as f:
            data = f.read().split('\n')

        self.assertEqual(len(data), 100)

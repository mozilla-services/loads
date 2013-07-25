import unittest
import psutil
from zmq.green.eventloop import ioloop
from loads.transport.brokerctrl import BrokerController, NotEnoughWorkersError


class Stream(object):
    msgs = []

    def send_multipart(self, msg):
        self.msgs.append(msg)


class FakeBroker(object):
    _backstream = Stream()


class TestBrokerController(unittest.TestCase):

    def setUp(self):
        loop = ioloop.IOLoop()
        broker = FakeBroker()
        self.ctrl = BrokerController(broker, loop)
        self.old_exists = psutil.pid_exists
        psutil.pid_exists = lambda pid: True

    def tearDown(self):
        psutil.pid_exists = self.old_exists
        Stream.msgs[:] = []

    def test_registration(self):
        self.ctrl.register_worker('1')
        self.assertTrue('1' in self.ctrl.workers)

        # make the worker busy before we unregister it
        self.ctrl.send_to_worker('1', ['something'])
        self.ctrl.reserve_workers(1, 'run')

        self.ctrl.unregister_worker('1')
        self.assertFalse('1' in self.ctrl.workers)

    def test_reserve_workers(self):
        self.ctrl.register_worker('1')
        self.ctrl.register_worker('2')

        self.assertRaises(NotEnoughWorkersError, self.ctrl.reserve_workers,
                          10, 'run')

        workers = self.ctrl.reserve_workers(2, 'run')
        workers.sort()
        self.assertEqual(workers, ['1', '2'])

    def test_run_and_stop(self):
        self.ctrl.register_worker('1')
        self.ctrl.register_worker('2')
        self.ctrl.register_worker('3')

        self.ctrl.reserve_workers(1, 'run')
        self.ctrl.reserve_workers(2, 'run2')

        runs = self.ctrl.list_runs().keys()
        runs.sort()
        self.assertEqual(['run', 'run2'], runs)
        self.ctrl.stop_run('run2', ['somemsg'])

        self.assertEqual(len(Stream.msgs), 5)

import unittest
import tempfile
import shutil

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
        self.dbdir = tempfile.mkdtemp()
        loop = ioloop.IOLoop()
        broker = FakeBroker()
        self.ctrl = BrokerController(broker, loop, dbdir=self.dbdir)
        self.old_exists = psutil.pid_exists
        psutil.pid_exists = lambda pid: True

    def tearDown(self):
        psutil.pid_exists = self.old_exists
        Stream.msgs[:] = []
        shutil.rmtree(self.dbdir)

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

    def test_db_access(self):
        self.ctrl.register_worker('1')
        self.ctrl.reserve_workers(1, 'run')

        # metadata
        data = {'some': 'data'}
        self.ctrl.save_metadata('run', data)
        self.assertEqual(self.ctrl.get_metadata('run'), data)

        # save data by worker
        self.ctrl.save_data('1', data)
        self.ctrl.flush_db()

        # we get extra run_id key, set for us
        self.assertEqual(data['run_id'], 'run')

        back = self.ctrl.get_data('run')
        self.assertTrue(back[0]['some'], 'data')

        back2 = self.ctrl.get_data('run')
        self.assertEqual(back, back2)

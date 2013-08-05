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
        dboptions = {'directory': self.dbdir}
        self.ctrl = BrokerController(broker, loop, dboptions=dboptions)
        self.old_exists = psutil.pid_exists
        psutil.pid_exists = lambda pid: True

    def tearDown(self):
        psutil.pid_exists = self.old_exists
        Stream.msgs[:] = []
        shutil.rmtree(self.dbdir)

    def test_registration(self):
        self.ctrl.register_agent('1')
        self.assertTrue('1' in self.ctrl.agents)

        # make the agent busy before we unregister it
        self.ctrl.send_to_agent('1', ['something'])
        self.ctrl.reserve_agents(1, 'run')

        self.ctrl.unregister_agent('1')
        self.assertFalse('1' in self.ctrl.agents)

    def test_reserve_agents(self):
        self.ctrl.register_agent('1')
        self.ctrl.register_agent('2')

        self.assertRaises(NotEnoughWorkersError, self.ctrl.reserve_agents,
                          10, 'run')

        agents = self.ctrl.reserve_agents(2, 'run')
        agents.sort()
        self.assertEqual(agents, ['1', '2'])

    def test_run_and_stop(self):
        self.ctrl.register_agent('1')
        self.ctrl.register_agent('2')
        self.ctrl.register_agent('3')

        self.ctrl.reserve_agents(1, 'run')
        self.ctrl.reserve_agents(2, 'run2')

        runs = self.ctrl.list_runs().keys()
        runs.sort()
        self.assertEqual(['run', 'run2'], runs)
        self.ctrl.stop_run('run2', ['somemsg'])

        self.assertEqual(len(Stream.msgs), 5)

    def test_db_access(self):
        self.ctrl.register_agent('1')
        self.ctrl.reserve_agents(1, 'run')

        # metadata
        data = {'some': 'data'}
        self.ctrl.save_metadata('run', data)
        self.assertEqual(self.ctrl.get_metadata('run'), data)

        # save data by agent
        self.ctrl.save_data('1', data)
        self.ctrl.flush_db()

        # we get extra run_id key, set for us
        self.assertEqual(data['run_id'], 'run')

        back = self.ctrl.get_data('run')
        self.assertTrue(back[0]['some'], 'data')

        back2 = self.ctrl.get_data('run')
        self.assertEqual(back, back2)

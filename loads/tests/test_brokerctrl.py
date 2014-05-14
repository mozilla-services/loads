import unittest2
import tempfile
import shutil
from collections import defaultdict
import time

import psutil
from zmq.green.eventloop import ioloop
from loads.util import json
from loads.transport.brokerctrl import (BrokerController,
                                        NotEnoughWorkersError,
                                        _compute_observers)


class Stream(object):
    msgs = []

    def send_multipart(self, msg):
        self.msgs.append(msg)

    send = send_multipart


class FakeBroker(object):
    _backend = _backstream = Stream()
    _publisher = Stream()
    pid = '123456'

    msgs = defaultdict(list)
    endpoints = {'receiver': 'xxx'}

    def send_json(self, target, msg):
        self.msgs[str(target)].append(msg)


class TestBrokerController(unittest2.TestCase):

    def setUp(self):
        self.dbdir = tempfile.mkdtemp()
        loop = ioloop.IOLoop()
        self.broker = FakeBroker()
        dboptions = {'directory': self.dbdir}
        self.ctrl = BrokerController(self.broker, loop, dboptions=dboptions)
        self.old_exists = psutil.pid_exists
        psutil.pid_exists = lambda pid: True

    def tearDown(self):
        psutil.pid_exists = self.old_exists
        Stream.msgs[:] = []
        shutil.rmtree(self.dbdir)

    def test_registration(self):
        self.ctrl.register_agent({'pid': '1', 'agent_id': '1'})
        self.assertTrue('1' in self.ctrl.agents)

        # make the agent busy before we unregister it
        self.ctrl.send_to_agent('1', ['something'])
        self.ctrl.reserve_agents(1, 'run')

        self.ctrl.unregister_agent('1')
        self.assertFalse('1' in self.ctrl.agents)

    def test_reserve_agents(self):
        self.ctrl.register_agent({'pid': '1', 'agent_id': '1'})
        self.ctrl.register_agent({'pid': '2', 'agent_id': '2'})

        self.assertRaises(NotEnoughWorkersError, self.ctrl.reserve_agents,
                          10, 'run')

        agents = self.ctrl.reserve_agents(2, 'run')
        agents.sort()
        self.assertEqual(agents, ['1', '2'])

    def test_run_and_stop(self):
        self.ctrl.register_agent({'pid': '1', 'agent_id': '1'})
        self.ctrl.register_agent({'pid': '2', 'agent_id': '2'})
        self.ctrl.register_agent({'pid': '3', 'agent_id': '3'})

        self.ctrl.reserve_agents(1, 'run')
        self.ctrl.reserve_agents(2, 'run2')

        runs = self.ctrl.list_runs(None, None).keys()
        runs.sort()
        self.assertEqual(['run', 'run2'], runs)
        self.ctrl.stop_run(['somemsg'], {'run_id': 'run'})

        # make sure the STOP cmd made it through
        msgs = [msg for msg in Stream.msgs if '_STATUS' not in msg[-1]]
        self.assertEqual(msgs[0][-1], '{"command":"STOP"}')
        self.assertEqual(len(msgs), 1)

    def test_db_access(self):
        self.ctrl.register_agent({'agent_id': '1', 'agent_id': '1'})
        self.ctrl.reserve_agents(1, 'run')

        # metadata
        data = {'some': 'data'}
        self.ctrl.save_metadata('run', data)
        self.assertEqual(self.ctrl.get_metadata(None, {'run_id': 'run'}),
                         data)

        # save data by agent
        self.ctrl.save_data('1', data)
        self.ctrl.flush_db()

        # we get extra run_id key, set for us
        self.assertEqual(data['run_id'], 'run')

        back = self.ctrl.get_data(None, {'run_id': 'run'})
        self.assertTrue(back[0]['some'], 'data')

        back2 = self.ctrl.get_data(None, {'run_id': 'run'})
        self.assertEqual(back, back2)

    def test_compute_observers(self):
        obs = ['irc', 'loads.observers.irc']
        observers = _compute_observers(obs)
        self.assertEqual(len(observers), 2)
        self.assertRaises(ImportError, _compute_observers, ['blah'])

    def test_run(self):
        msg = ['somedata', '', 'target']
        data = {'agents': 1, 'args': {}}

        # not enough agents
        self.ctrl.run(msg, data)
        res = self.broker.msgs.values()[0]
        self.assertEqual(res, [{'error': 'Not enough agents'}])

        # one agent, we're good
        self.ctrl._agents['agent1'] = {'pid': '1234'}
        self.ctrl.run(msg, data)
        runs = self.broker.msgs.values()[0][-1]
        self.assertEqual(runs['result']['agents'], ['agent1'])

    def test_run_command(self):
        msg = ['somedata', '', 'target']
        data = {'agents': 1, 'args': {}, 'agent_id': '1'}
        self.ctrl.run_command('RUN', msg, data)
        self.ctrl.run_command('AGENT_STATUS', msg, data)
        runs = self.broker.msgs.values()[0][-1]
        self.assertEqual(runs['result']['agents'], ['agent1'])

        msg = {"command": "_STATUS", "args": {}, "agents": 1, "agent_id": "1"}
        msg = msg.items()
        msg.sort()

        self.assertTrue(len(self.broker._backstream.msgs), 1)
        self.assertTrue(len(self.broker._backstream.msgs[0]), 1)
        got = self.broker._backstream.msgs[0][-1]
        got = json.loads(got)
        got = got.items()
        got.sort()
        self.assertEqual(msg, got)

    def test_clean(self):
        self.ctrl.agent_timeout = 0.1
        self.ctrl._associate('run', ['1', '2'])
        self.ctrl.clean()
        self.assertTrue('1' in self.ctrl._agent_times)
        self.assertTrue('2' in self.ctrl._agent_times)

        time.sleep(.2)
        self.ctrl.clean()

        self.assertEqual(self.ctrl._agent_times, {})
        self.ctrl.test_ended('run')

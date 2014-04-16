from unittest import TestCase
import time

import mock
from zmq.eventloop import ioloop

from loads.runners import ExternalRunner as ExternalRunner_
from loads.util import json


class ExternalRunner(ExternalRunner_):
    """Subclass the ExternalRunner to be sure we don't use the std output in
    the tests unless asked especially to do so."""

    def register_output(self, output_name):
        pass


class FakeProcess(object):
    """Mimics the API of subprocess.Popen"""

    def __init__(self, running=True, options=None):
        self._running = running
        self.terminated = False
        self.options = options
        self.returncode = 0

    def poll(self):
        if self._running:
            return None
        else:
            return 1

    def terminate(self):
        self.terminated = True


class TestExternalRunner(TestCase):

    def test_step_hits(self):
        runner = ExternalRunner({'hits': [1, 2, 10]})
        self.assertEquals(runner.step_hits, 1)

        runner._current_step += 1
        self.assertEquals(runner.step_hits, 2)

        runner._current_step += 1
        self.assertEquals(runner.step_hits, 10)

        runner._current_step += 1
        self.assertEquals(runner.step_hits, 10)

    def test_step_users(self):
        runner = ExternalRunner({'users': [1, 2, 10]})
        self.assertEquals(runner.step_users, 1)

        runner._current_step += 1
        self.assertEquals(runner.step_users, 2)

        runner._current_step += 1
        self.assertEquals(runner.step_users, 10)

        runner._current_step += 1
        self.assertEquals(runner.step_users, 10)

    def test_nb_steps(self):
        runner = ExternalRunner({'users': [1, 2, 10]})
        self.assertEquals(runner._nb_steps, 3)

        runner = ExternalRunner({'hits': [1, 2, 10]})
        self.assertEquals(runner._nb_steps, 3)

        runner = ExternalRunner({'users': [1, 2, 10],
                                 'hits': [1, 2, 3, 4]})
        self.assertEquals(runner._nb_steps, 4)

    def test_check_processes_waits_for_step_to_complete(self):
        runner = ExternalRunner()
        runner._start_next_step = mock.MagicMock()
        runner._step_started_at = time.time()

        runner._processes = [FakeProcess(running=False),
                             FakeProcess(running=True)]
        runner._check_processes()
        self.assertFalse(runner._start_next_step.called)

        runner._processes[0]._running = False
        runner._check_processes()
        self.assertTrue(runner._start_next_step.called)

    def test_check_processes_ends_step_if_procs_time_out(self):
        runner = ExternalRunner({'process_timeout': 2})
        runner._start_next_step = mock.MagicMock()
        runner._step_started_at = time.time() - 5

        runner._processes = [FakeProcess(running=False),
                             FakeProcess(running=True)]
        runner._check_processes()
        self.assertTrue(runner._start_next_step.called)

    def test_check_processes_reaps_pending_processes(self):
        runner = ExternalRunner()
        runner._start_next_step = mock.MagicMock()
        runner._step_started_at = time.time()

        runner._processes_pending_cleanup = [FakeProcess(running=True),
                                             FakeProcess(running=False)]
        runner._check_processes()
        self.assertEquals(len(runner._processes_pending_cleanup), 1)

    def test_processes_are_reaped_at_end_of_step(self):
        runner = ExternalRunner()
        runner.stop_run = mock.MagicMock()
        runner._current_step = 1
        runner._nb_steps = 1

        procs = [FakeProcess(running=True), FakeProcess(running=False)]
        runner._processes = procs
        runner._start_next_step()
        self.assertTrue(procs[0].terminated)
        self.assertFalse(procs[1].terminated)
        self.assertEquals(len(runner._processes), 0)
        self.assertTrue(procs[0] in runner._processes_pending_cleanup)

    def test_runner_is_reinitialized_on_each_step(self):
        runner = ExternalRunner()
        runner.stop_run = mock.MagicMock()
        runner.spawn_external_runner = mock.MagicMock()

        runner._current_step = 0
        runner._nb_steps = 2
        self.assertTrue(runner._step_started_at is None)

        runner._start_next_step()
        self.assertFalse(runner.stop_run.called)
        self.assertEqual(runner._current_step, 1)
        self.assertTrue(runner._step_started_at is not None)

        runner._step_started_at = None
        runner._start_next_step()
        self.assertFalse(runner.stop_run.called)
        self.assertEqual(runner._current_step, 2)
        self.assertTrue(runner._step_started_at is not None)

        runner._start_next_step()
        self.assertTrue(runner.stop_run.called)

    def test_messages_are_relayed(self):
        runner = ExternalRunner()
        runner._test_result = mock.MagicMock()
        data = json.dumps({'data_type': 'foo', 'bar': 'barbaz', 'run_id': 1})
        runner._process_result([data, ])
        runner.test_result.foo.assertCalledWith(bar='barbaz')

    def test_execute(self):
        loop = ioloop.IOLoop()
        loop.start = mock.Mock()
        runner = ExternalRunner({'hits': [2], 'users': [2]}, loop)
        runner._prepare_filesystem = mock.Mock()
        runner.spawn_external_runner = mock.Mock()

        runner._execute()

        self.assertTrue(loop.start.called)
        self.assertTrue(runner._prepare_filesystem.called)
        self.assertEquals(runner.spawn_external_runner.call_count, 2)

    def test_execute_step_users(self):
        loop = ioloop.IOLoop()
        loop.start = mock.Mock()
        runner = ExternalRunner({'hits': [1], 'users': [1, 3, 5]}, loop)
        runner._prepare_filesystem = mock.Mock()
        runner.spawn_external_runner = mock.Mock()

        runner._execute()
        self.assertTrue(loop.start.called)
        self.assertTrue(runner._prepare_filesystem.called)
        self.assertEquals(runner.spawn_external_runner.call_count, 1)

        runner._start_next_step()
        self.assertEquals(runner.spawn_external_runner.call_count, 4)

        runner._start_next_step()
        self.assertEquals(runner.spawn_external_runner.call_count, 9)

    @mock.patch('loads.runners.external.subprocess.Popen',
                lambda *args, **kwargs: FakeProcess(options=(args, kwargs)))
    def test_spawn_external_runner(self):
        runner = ExternalRunner({'test_runner': 'foobar', 'hits': [2, 3],
                                 'users': [2, 4], 'fqn': 'baz'})
        runner.spawn_external_runner(1)
        self.assertEquals(len(runner._processes), 1)

        args, kwargs = runner._processes[0].options
        self.assertTrue(['foobar'] in args)
        loads_options = [e for e in kwargs['env'] if e.startswith('LOADS_')]
        loads_options.sort()
        self.assertEquals(loads_options,
                          ["LOADS_AGENT_ID", "LOADS_CURRENT_USER",
                           "LOADS_RUN_ID", "LOADS_TOTAL_HITS",
                           "LOADS_TOTAL_USERS", "LOADS_ZMQ_RECEIVER"])

    @mock.patch('loads.runners.external.subprocess.Popen',
                lambda *args, **kwargs: FakeProcess(options=(args, kwargs)))
    def test_spawn_external_runner_with_duration(self):
        runner = ExternalRunner({'test_runner': 'foobar', 'duration': 5,
                                 'users': [2, 4], 'fqn': 'baz'})
        runner.spawn_external_runner(1)
        self.assertEquals(len(runner._processes), 1)

        args, kwargs = runner._processes[0].options
        self.assertTrue(['foobar'] in args)
        loads_options = [e for e in kwargs['env'] if e.startswith('LOADS_')]
        loads_options.sort()
        self.assertEquals(loads_options,
                          ["LOADS_AGENT_ID", "LOADS_CURRENT_USER",
                           "LOADS_DURATION", "LOADS_RUN_ID",
                           "LOADS_TOTAL_USERS", "LOADS_ZMQ_RECEIVER"])

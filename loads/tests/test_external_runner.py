from unittest import TestCase
import datetime

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

    def test_check_processes_wait(self):
        runner = ExternalRunner()
        runner._start_next_step = mock.MagicMock()
        runner._run_started_at = datetime.datetime.now()

        runner._processes = [FakeProcess(running=False),
                             FakeProcess(running=True)]
        runner._check_processes()
        self.assertFalse(runner._start_next_step.called)

    def test_check_processes_timeouts(self):
        runner = ExternalRunner({'process_timeout': 2})
        runner._start_next_step = mock.MagicMock()
        runner._run_started_at = (
            datetime.datetime.now() - datetime.timedelta(seconds=5))

        runner._processes = [FakeProcess(running=False),
                             FakeProcess(running=True)]
        runner._check_processes()
        self.assertTrue(runner._start_next_step.called)

    def test_check_processes_finishes(self):
        runner = ExternalRunner()
        runner._start_next_step = mock.MagicMock()
        runner._run_started_at = datetime.datetime.now()

        runner._processes = [FakeProcess(running=True),
                             FakeProcess(running=True)]
        runner._check_processes()
        self.assertFalse(runner._start_next_step.called)

    def test_check_processes_respawn_when_using_duration(self):
        runner = ExternalRunner({'duration': 5})
        runner._start_next_step = mock.MagicMock()
        runner.spawn_external_runner = mock.MagicMock()
        runner._run_started_at = datetime.datetime.now()

        runner._processes = [FakeProcess(running=False),
                             FakeProcess(running=False)]
        runner._check_processes()
        self.assertTrue(runner.spawn_external_runner.called)
        self.assertEquals(2, runner.spawn_external_runner.call_count)
        self.assertFalse(runner._start_next_step.called)

    def test_check_processes_stop_respawning_when_duration_is_over(self):
        runner = ExternalRunner({'duration': 5})
        runner._start_next_step = mock.MagicMock()
        runner.spawn_external_runner = mock.MagicMock()
        runner._run_started_at = (
            datetime.datetime.now() - datetime.timedelta(seconds=10))

        runner._processes = [FakeProcess(running=False),
                             FakeProcess(running=False)]
        runner._check_processes()
        self.assertFalse(runner.spawn_external_runner.called)
        self.assertTrue(runner._start_next_step.called)

    def test_check_processes_adds_pending_processes(self):
        runner = ExternalRunner()
        runner._start_next_step = mock.MagicMock()
        runner.spawn_external_runner = mock.MagicMock()
        runner._run_started_at = datetime.datetime.now()

        runner._processes_pending_cleanup = [FakeProcess(running=True),
                                             FakeProcess(running=False)]
        runner._check_processes()
        self.assertEquals(len(runner._processes_pending_cleanup), 1)

    def test_processes_are_reaped(self):
        runner = ExternalRunner()
        runner.stop_run = mock.MagicMock()
        runner._current_step = 0
        runner._nb_steps = 1

        procs = [FakeProcess(running=True), FakeProcess(running=False)]
        runner._processes = procs
        runner._start_next_step()
        self.assertTrue(procs[0].terminated)
        self.assertFalse(procs[1].terminated)
        self.assertEquals(len(runner._processes), 0)
        self.assertTrue(procs[0] in runner._processes_pending_cleanup)

    def test_runner_is_reinitialized(self):
        runner = ExternalRunner()
        runner.stop_run = mock.MagicMock()
        runner._initialize = mock.MagicMock()
        runner.spawn_external_runner = mock.MagicMock()

        runner._current_step = 0
        runner._nb_steps = 2

        runner._start_next_step()
        self.assertFalse(runner.stop_run.called)
        self.assertTrue(runner._initialize.called)

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

        self.assertTrue(runner._prepare_filesystem.called)
        self.assertEquals(runner.spawn_external_runner.call_count, 4)

    @mock.patch('loads.runners.external.subprocess.Popen',
                lambda *args, **kwargs: FakeProcess(options=(args, kwargs)))
    def test_spawn_external_runner(self):
        runner = ExternalRunner({'test_runner': 'foobar', 'hits': [2, 3],
                                 'users': [2, 4], 'fqn': 'baz'})
        runner.spawn_external_runner()
        self.assertEquals(len(runner._processes), 1)

        args, kwargs = runner._processes[0].options
        self.assertTrue(['foobar'] in args)
        loads_options = [e for e in kwargs['env'] if e.startswith('LOADS_')]
        self.assertEquals(len(loads_options), 4)

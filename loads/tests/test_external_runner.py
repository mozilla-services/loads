from unittest import TestCase
import datetime

import mock

from loads.runners import ExternalRunner


class FakeProcess(object):
    """Mimics the API of subprocess.Popen"""

    def __init__(self, running=True):
        self._running = running

    def poll(self):
        if self._running:
            return None
        else:
            return 1


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
        runner = ExternalRunner({})
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
        runner = ExternalRunner({})
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

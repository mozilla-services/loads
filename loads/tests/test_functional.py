# Contains functional tests for loads.
# It runs the tests located in the example directory.
#
# Try to run loads for all the combinaison possible:
# - normal local run
# - normal distributed run
# - run via nosetest
# - run with cycles / users

from unittest import TestCase
import sys
import subprocess
import time

from loads.runner import run as start_runner
from loads.tests.support import get_runner_args


class FunctionalTest(TestCase):

    def setUp(self):
        devnull = open('/dev/null', 'w')
        cmd = [sys.executable, '-m', 'loads.examples.echo_server']
        self._server = subprocess.Popen(cmd, stdout=devnull, stderr=devnull)

    def tearDown(self):
        self._server.kill()

    def test_normal_run(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            output='null'))

    def test_normal_run_with_users_and_cycles(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            output='null', users=10, cycles=5))


class DistributedFunctionalTest(TestCase):

    def setUp(self):
        self._processes = []
        self._start_cmd('loads.examples.echo_server')
        self._start_cmd('loads.transport.broker')
        for x in range(3):
            self._start_cmd('loads.transport.agent')
        time.sleep(2)  # Wait for the registration to happen

    def _start_cmd(self, cmd):
        devnull = open('/dev/null', 'w')
        process = subprocess.Popen([sys.executable, '-m', cmd],
                                   stdout=devnull, stderr=devnull)
        self._processes.append(process)

    def tearDown(self):
        for process in self._processes:
            process.kill()

    def test_distributed_run(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=2, output='null', users=1, cycles=1))

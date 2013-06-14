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
#import subprocess
import time

import requests
from gevent import subprocess

from loads.runner import run as start_runner
from loads.tests.support import get_runner_args
from loads.transport.client import Client


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
        try:
            self._start_cmd('loads.transport.broker')
            for x in range(3):
                self._start_cmd('loads.transport.agent')
            self._start_cmd('loads.examples.echo_server')

            # wait for the echo server to be started
            try:
                requests.get('http://0.0.0.0:9000')
            except requests.ConnectionError:
                time.sleep(.1)

            # wait for the broker to be up with 3 slaves.
            self.client = Client()
            while len(self.client.list()) != 3:
                time.sleep(.1)
        except Exception:
            self.tearDown()
            raise

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
            agents=2,
            output='null',
            users=1, cycles=10))

        data = self.client.get_data()
        self.assertTrue(len(data) > 100)

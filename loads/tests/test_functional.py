# Contains functional tests for loads.
# It runs the tests located in the example directory.
#
# Try to run loads for all the combinaison possible:
# - normal local run
# - normal distributed run
# - run via nosetest
# - run with cycles / users
import os
import time
import requests

from unittest2 import TestCase, skipIf

from loads.main import run as start_runner
from loads.runner import Runner
from loads.tests.support import get_runner_args, start_process
from loads.transport.client import Client
from loads.transport.util import DEFAULT_FRONTEND


_EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), os.pardir, 'examples')
_RUNNING = False


def start_servers():
    global _RUNNING
    if _RUNNING:
        return

    start_process('loads.transport.broker')
    for x in range(3):
        start_process('loads.transport.agent')
    start_process('loads.examples.echo_server')

    # wait for the echo server to be started
    tries = 0
    while True:
        try:
            requests.get('http://0.0.0.0:9000')
            break
        except requests.ConnectionError:
            time.sleep(.5)
            tries += 1
            if tries > 3:
                raise

    # wait for the broker to be up with 3 slaves.
    client = Client()
    while len(client.list()) != 3:
        time.sleep(.1)

    # control that the broker is responsive
    client.ping()
    for wid in client.list():
        status = client.status(wid)['status']
        assert status == {}, status

    client.close()
    _RUNNING = True


class FunctionalTest(TestCase):

    def setUp(self):
        start_servers()

    @skipIf('TRAVIS' in os.environ, 'Travis')
    def test_normal_run(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            output=['null']))

    @skipIf('TRAVIS' in os.environ, 'Travis')
    def test_normal_run_with_users_and_cycles(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            output=['null'], users=10, cycles=5))

    @skipIf('TRAVIS' in os.environ, 'Travis')
    def test_concurent_session_access(self):
        runner = Runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_concurrency',
            output=['null'], users=10))
        runner.execute()
        assert runner.test_result.nb_success == 10
        assert runner.test_result.nb_errors == 0
        assert runner.test_result.nb_failures == 0

    @skipIf('TRAVIS' in os.environ, 'Travis')
    def test_duration_updates_counters(self):
        runner = Runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_concurrency',
            output=['null'], duration=1.))
        runner.execute()
        assert runner.test_result.nb_success > 2


class DistributedFunctionalTest(TestCase):
    def setUp(self):
        start_servers()
        self.client = Client()

    @skipIf('TRAVIS' in os.environ, 'Travis')
    def test_distributed_run(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=2,
            output=['null'],
            users=1, cycles=10))

        runs = self.client.list_runs()
        data = self.client.get_data(runs.keys()[0])
        self.assertTrue(len(data) > 100)

    @skipIf('TRAVIS' in os.environ, 'Travis')
    def test_distributed_run_duration(self):
        args = get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=1,
            #output=['null'],
            users=10,
            duration=1)

        start_runner(args)
        time.sleep(1.)
        runs = self.client.list_runs()
        try:
            data = self.client.get_data(runs.keys()[0])
        except Exception:
            data = self.client.get_data(runs.keys()[0])
        self.assertTrue(len(data) > 10)

    @skipIf('TRAVIS' in os.environ, 'Travis')
    def test_distributed_detach(self):
        args = get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=1,
            #output=['null'],
            users=10,
            duration=2)

        # simulate a ctrl+c
        def _recv(self, msg):
            raise KeyboardInterrupt

        from loads.distributed import DistributedRunner
        old = DistributedRunner._recv_result
        DistributedRunner._recv_result = _recv

        # simulate a 'detach' answer
        def _raw_input(msg):
            return 'd'

        from loads import main
        main.raw_input = _raw_input

        # start the runner
        start_runner(args)
        time.sleep(1.)

        # now reattach the console
        DistributedRunner._recv_result = old
        start_runner({'attach': True, 'broker': DEFAULT_FRONTEND,
                      'output': ['null']})

        runs = self.client.list_runs()
        try:
            data = self.client.get_data(runs.keys()[0])
        except Exception:
            data = self.client.get_data(runs.keys()[0])
        self.assertTrue(len(data) > 10)

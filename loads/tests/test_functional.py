# Contains functional tests for loads.
# It runs the tests located in the example directory.
#
# Try to run loads for all the combinaison possible:
# - normal local run
# - normal distributed run
# - run via nosetest
# - run with cycles / users
from unittest2 import TestCase

import atexit
import os
import sys
import time
import requests

from gevent import subprocess

from loads.runner import run as start_runner
from loads.tests.support import get_runner_args, start_process
from loads.transport.client import Client


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
            time.sleep(.3)
            tries += 1
            if tries > 3:
                raise

    # wait for the broker to be up with 3 slaves.
    client = Client()
    while len(client.list()) != 3:
        time.sleep(.1)

    client.close()
    _RUNNING = True



class FunctionalTest(TestCase):

    def setUp(self):
        start_servers()

    def test_normal_run(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            output=['null']))

    def test_normal_run_with_users_and_cycles(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            output=['null'], users=10, cycles=5))


class DistributedFunctionalTest(TestCase):
    def setUp(self):
        start_servers()
        self.client = Client()

    def test_distributed_run(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=2,
            output=['null'],
            users=1, cycles=10))

        runs = self.client.list_runs()
        data = self.client.get_data(runs.keys()[0])
        self.assertTrue(len(data) > 100)

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

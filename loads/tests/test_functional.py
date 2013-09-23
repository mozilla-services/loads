# Contains functional tests for loads.
# It runs the tests located in the example directory.
#
# Try to run loads for all the combinaison possible:
# - normal local run
# - normal distributed run
# - run via nosetest
# - run with hits / users
import os
import time
import requests
import tempfile
import shutil
import sys

from unittest2 import TestCase, skipIf

from loads.main import run as start_runner
from loads.runners import LocalRunner, DistributedRunner
from loads.tests.support import (get_runner_args, start_process, stop_process,
                                 hush)
from loads.transport.client import Pool, Client
from loads.transport.util import DEFAULT_FRONTEND, verify_broker


_EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), os.pardir, 'examples')
_RESULTS = os.path.join(os.path.dirname(__file__), 'observers')


def observer(results, conf):
    with open(_RESULTS, 'a+') as f:
        f.write(str(results) + '\n')


def observer_fail(results, conf):
    raise ValueError("Boom")


def start_servers():
    procs = []

    procs.append(start_process('loads.transport.broker'))

    for x in range(3):
        procs.append(start_process('loads.transport.agent'))

    procs.append(start_process('loads.examples.echo_server'))

    # wait for the echo server to be started
    tries = 0
    while True:
        try:
            requests.get('http://0.0.0.0:9000')
            break
        except requests.ConnectionError:
            time.sleep(.2)
            tries += 1
            if tries > 20:
                raise

    # wait for the broker to be up with 3 slaves.
    client = Pool()
    while len(client.list()) != 3:
        time.sleep(.1)

    # control that the broker is responsive
    client.ping()
    for wid in client.list():
        status = client.status(wid)['status']
        assert status == {}, status

    client.close()

    if verify_broker() is None:
        raise ValueError('Broker seem down')

    return procs


class FunctionalTest(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.procs = start_servers()
        cls.client = Client()
        cls.location = os.getcwd()
        cls.dirs = []

    @classmethod
    def tearDownClass(cls):
        for proc in cls.procs:
            stop_process(proc)
        os.chdir(cls.location)
        for dir in cls.dirs:
            shutil.rmtree(dir)
        if os.path.exists(_RESULTS):
            os.remove(_RESULTS)

    def tearDown(self):
        runs = self.client.list_runs()
        for run_id in runs:
            if not isinstance(run_id, basestring):
                continue
            self.client.stop_run(run_id)

    def test_normal_run(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            output=['null']))

    def test_file_output(self):
        fqn = 'loads.examples.test_blog.TestWebSite.test_something'
        args = get_runner_args(fqn=fqn, output=['file'])
        fd, args['output_file_filename'] = tempfile.mkstemp()
        os.close(fd)
        try:
            start_runner(args)
        finally:
            os.remove(args['output_file_filename'])

    def test_normal_run_with_users_and_hits(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            output=['null'], users=2, hits=2))

    def test_concurent_session_access(self):
        runner = LocalRunner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_concurrency',
            output=['null'], users=2))
        runner.execute()
        nb_success = runner.test_result.nb_success
        assert nb_success == 2, nb_success
        assert runner.test_result.nb_errors == 0
        assert runner.test_result.nb_failures == 0
        assert runner.test_result.get_counter('lavabo') == 2
        assert runner.test_result.get_counter('beau') == 2

    def test_duration_updates_counters(self):
        runner = LocalRunner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_concurrency',
            output=['null'], duration=2.))
        runner.execute()
        nb_success = runner.test_result.nb_success
        assert nb_success > 2, nb_success

    def test_distributed_run(self):
        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=2,
            output=['null'],
            observer=['loads.tests.test_functional.observer',
                      'loads.tests.test_functional.observer_fail'],
            users=1, hits=5))

        client = Pool()
        runs = client.list_runs()
        run_id = runs.keys()[0]
        client.stop_run(run_id)

        # checking the data
        data = client.get_data(run_id)
        self.assertTrue(len(data) > 25, len(data))
        self.assertEqual(client.get_urls(run_id),
                         {u'http://127.0.0.1:9000/': 10})
        counts = dict(client.get_counts(run_id))
        self.assertEquals(counts['socket_open'], 10)
        self.assertEquals(counts['socket_close'], 10)

        # making sure the observer was called
        with open(_RESULTS) as f:
            data = f.readlines()

        assert len(data) > 0, data

    def test_distributed_run_duration(self):
        args = get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=1,
            output=['null'],
            users=1,
            duration=2)

        start_runner(args)

        client = Pool()

        for i in range(10):
            runs = client.list_runs()
            time.sleep(.1)
            data = client.get_data(runs.keys()[0])
            if len(data) > 0:
                return

        raise AssertionError('No data back')

    def test_distributed_run_external_runner(self):
        args = get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=1,
            users=1,
            test_runner='%s -m loads.tests.runner {test}' % sys.executable)

        start_runner(args)
        client = Pool()
        runs = client.list_runs()
        data = client.get_data(runs.keys()[0])
        self.assertTrue(len(data) > 5, len(data))

    def test_distributed_detach(self):
        time.sleep(.5)

        args = get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=1,
            users=1,
            output=['null'],
            duration=2)

        # simulate a ctrl+c
        def _recv(self, msg):
            raise KeyboardInterrupt

        old = DistributedRunner._recv_result
        DistributedRunner._recv_result = _recv

        # simulate a 'detach' answer
        def _raw_input(msg):
            return 'detach'

        from loads import main
        main.raw_input = _raw_input

        # start the runner
        start_runner(args)
        # we detached.
        time.sleep(.2)

        # now reattach the console
        DistributedRunner._recv_result = old
        start_runner({'attach': True, 'broker': DEFAULT_FRONTEND,
                      'output': ['null']})

        # the test is over
        for i in range(5):
            time.sleep(.1)
            runs = self.client.list_runs()
            if len(runs) == 0:
                continue
            data = self.client.get_data(runs.keys()[0])
            if len(data) > 0:
                return
        raise AssertionError('No data back')

    @classmethod
    def _get_dir(self):
        dir = tempfile.mkdtemp()
        self.dirs.append(dir)
        return dir

    @hush
    @skipIf(sys.version[1] == '6', 'Fails under 2.6')
    def test_file_copy_test_file(self):
        test_dir = self._get_dir()
        os.chdir(os.path.dirname(__file__))

        args = get_runner_args(
            fqn='test_here.TestWebSite.test_something',
            agents=1,
            users=1,
            hits=1,
            test_dir=test_dir,
            include_file=['test_here.py'])

        start_runner(args)
        data = []

        for i in range(20):
            runs = self.client.list_runs()
            if len(runs) == 0:
                time.sleep(.1)
                continue
            try:
                data = self.client.get_data(runs.keys()[-1])
            except Exception:
                raise AssertionError(str(runs))

            if len(data) > 0:
                break
            time.sleep(.1)

        # check that we got in the dir
        content = os.listdir(test_dir)
        self.assertTrue('test_here.py' in content, content)

        if data == []:
            raise AssertionError('No data back')

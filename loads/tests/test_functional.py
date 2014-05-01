# Contains functional tests for loads.
# It runs the tests located in the example directory.
#
# Try to run loads for all the combinaison possible:
# - normal local run
# - normal distributed run
# - run via nosetest
# - run with hits / users
import os
import errno
import time
import requests
import tempfile
import shutil
import sys
import zipfile
from cStringIO import StringIO

from unittest2 import TestCase, skipIf

from zmq.green.eventloop import ioloop

from loads.db._python import BrokerDB
from loads.main import run as start_runner
from loads.runners import LocalRunner, DistributedRunner
from loads.tests.support import (get_runner_args, start_process, stop_process,
                                 hush)
from loads.transport.client import Pool, Client
from loads.transport.util import DEFAULT_FRONTEND, verify_broker


_EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), os.pardir, 'examples')
_RESULTS = os.path.join(os.path.dirname(__file__), 'observers')


class Observer(object):
    name = 'dummy'
    options = {}

    def __init__(self, *args, **kw):
        pass

    def __call__(self, results):
        with open(_RESULTS, 'a+') as f:
            f.write(str(results) + '\n')


class ObserverFail(Observer):

    def __call__(self, results):
        raise ValueError("Boom")


_PROCS = []


def start_servers():
    if len(_PROCS) != 0:
        return _PROCS

    _PROCS.append(start_process('loads.transport.broker', '--db', 'python',
                                '--heartbeat', 'tcp://0.0.0.0:9876'))

    for x in range(10):
        _PROCS.append(start_process('loads.transport.agent'))

    _PROCS.append(start_process('loads.examples.echo_server'))

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
    while len(client.list()) != 10:
        time.sleep(.1)

    # control that the broker is responsive
    client.ping()
    for wid in client.list():
        status = client.status(wid)['status']
        assert status == {}, status

    client.close()

    if verify_broker() is None:
        raise ValueError('Broker seem down')

    return _PROCS


def stop_servers():
    for proc in _PROCS:
        stop_process(proc)
    _PROCS[:] = []


@skipIf('TRAVIS' in os.environ, 'deactivated in Travis')
class FunctionalTest(TestCase):

    @classmethod
    def setUpClass(cls):
        if 'TRAVIS' in os.environ:
            return
        start_servers()
        cls.client = Client()
        cls.location = os.getcwd()
        cls.loop = ioloop.IOLoop()
        cls.dirs = []
        cls.db = BrokerDB(cls.loop, db='python')

    @classmethod
    def tearDownClass(cls):
        if 'TRAVIS' in os.environ:
            return
        stop_servers()
        os.chdir(cls.location)
        for dir in cls.dirs:
            if os.path.exists(dir):
                shutil.rmtree(dir)

        if os.path.exists(_RESULTS):
            os.remove(_RESULTS)

    def tearDown(self):
        runs = self.client.list_runs()
        for run_id in runs:
            if not isinstance(run_id, basestring):
                continue
            self.client.stop_run(run_id)

    def _get_client(self):
        client = Pool()
        while len(client.list_runs()) > 0:
            time.sleep(.2)
        return client

    def _wait_run_started(self, client=None):
        if client is None:
            client = self.client
        while len(client.list_runs()) == 0:
            time.sleep(.2)
        return client.list_runs().items()[0]

    def _wait_run_over(self, client=None):
        if client is None:
            client = self.client
        while len(client.list_runs()) > 0:
            time.sleep(.2)

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
        client = self._get_client()

        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=2,
            project_name='test_distributed_run',
            output=['null'],
            observer=['loads.tests.test_functional.Observer',
                      'loads.tests.test_functional.ObserverFail'],
            users=1, hits=5))

        runs = client.list_runs()
        run_id = runs.keys()[0]
        client.stop_run(run_id)

        # checking the metadata
        metadata = client.get_metadata(run_id)
        self.assertEqual(metadata['project_name'], 'test_distributed_run')

        # wait for the run to end
        self._wait_run_over(client)

        # checking the data
        # the run is over so the detailed lines where pruned
        self.assertRaises(ValueError, client.get_data, run_id)
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
        client = self._get_client()

        args = get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=1,
            output=['null'],
            users=1,
            duration=2)

        start_runner(args)

        for i in range(10):
            runs = client.list_runs()
            time.sleep(.1)
            data = client.get_metadata(runs.keys()[0])
            if len(data) > 0:
                return

        raise AssertionError('No data back')

    def test_distributed_run_external_runner(self):
        client = self._get_client()

        args = get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_something',
            agents=1,
            users=1,
            test_runner='%s -m loads.tests.runner {test}' % sys.executable)

        start_runner(args)

        # getting the run_id
        runs = self.client.list_runs()
        while runs == []:
            runs = self.client.list_runs()
        run_id = runs.keys()[0]

        data = client.get_metadata(run_id)
        self.assertTrue(len(data) > 5, len(data))

    def test_distributed_detach(self):
        client = self._get_client()

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

        # getting the run_id
        run_id, _ = self._wait_run_started()

        # we detached.
        time.sleep(.2)

        # now reattach the console
        DistributedRunner._recv_result = old
        start_runner({'attach': True, 'broker': DEFAULT_FRONTEND,
                      'output': ['null']})

        # now waiting for the test to be over
        self._wait_run_over(client)

        # now let's see the metadata
        data = client.get_metadata(run_id)
        self.assertTrue(len(data) > 5, len(data))

    @classmethod
    def _get_dir(self):
        dir = tempfile.mkdtemp()
        self.dirs.append(dir)
        return dir

    @hush
    def test_file_copy_test_file(self):
        client = self._get_client()
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

        run_id, agents = self._wait_run_started(client)
        self._wait_run_over(client)
        data = self.client.get_metadata(run_id)

        # check that we got in the dir
        real_test_dir = test_dir + agents[0][0]
        self.dirs.append(real_test_dir)
        content = os.listdir(real_test_dir)
        self.assertTrue('test_here.py' in content, content)

        if data == []:
            raise AssertionError('No data back')

    def test_sending_crap_ujson(self):
        test_dir = self._get_dir()
        os.chdir(os.path.dirname(__file__))

        data = StringIO()
        filepath = 'test_here.py'
        zf = zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED)
        info = zipfile.ZipInfo('test_here.py')
        info.external_attr = os.stat(filepath).st_mode << 16L

        with open(filepath) as f:
            zf.writestr(info, f.read())

        zf.close()
        data = data.getvalue()

        args = get_runner_args(
            fqn='test_here.TestWebSite.test_something',
            agents=1,
            users=1,
            hits=1,
            test_dir=test_dir,
            include_file=['test_here.py'])

        args['crap'] = data
        self.assertRaises(ValueError, start_runner, args)

    def test_errors(self):
        client = self._get_client()

        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_will_error',
            agents=1,
            project_name='test_distributed_run',
            output=['null'],
            observer=['loads.tests.test_functional.Observer',
                      'loads.tests.test_functional.ObserverFail'],
            users=1, hits=5))
        run_id, _ = self._wait_run_started(client)
        client.stop_run(run_id)

        # checking the metadata
        metadata = client.get_metadata(run_id)
        self.assertEqual(metadata['project_name'], 'test_distributed_run')

        # checking the data
        # the run is over so the detailed lines where pruned
        # but we have all errors
        errors = list(self.db.get_errors(run_id))
        self.assertTrue(len(errors) > 0)

    def is_running(self, pid):
        try:
            os.kill(pid, 0)
        except OSError as err:
            if err.errno == errno.ESRCH:
                return False
        return True

    @hush
    def test_die(self):
        # make sure a recalcitrant process gets eventually killed
        client = self._get_client()

        start_runner(get_runner_args(
            fqn='loads.examples.test_blog.TestWebSite.test_wontdie',
            agents=1,
            project_name='test_distributed_run',
            output=['null'],
            users=1, duration=200,
            detach=True))

        run_id, agents = self._wait_run_started(client)

        agent_id = agents[0][0]

        # get the pid of the worker
        status = client.status(agent_id)

        while status['status'] == {}:
            status = client.status(agent_id)
            print status

        worker_pid = int(status['status'].keys()[0])

        # force a stop
        client.stop_run(run_id)

        # we want to make sure the pid is gone in a 6s frame
        start = time.time()
        dead = not self.is_running(worker_pid)
        while not dead and time.time() - start < 6:
            dead = not self.is_running(worker_pid)

        self.assertTrue(dead)
        self._wait_run_over(client)

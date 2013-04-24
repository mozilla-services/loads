# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import unittest
import logging
import os
import tempfile
import time

import psutil

from loads import get_cluster
from loads.exc import ExecutionError, TimeoutError
from loads import client


logger = logging.getLogger('loads')


class TestCluster(unittest.TestCase):

    def setUp(self):
        self.clusters = []
        self.files = []
        self.old_timeout = client.DEFAULT_TIMEOUT
        self.old_movf = client.DEFAULT_TIMEOUT_MOVF
        self.old_ovf = client.DEFAULT_TIMEOUT_OVF
        client.DEFAULT_TIMEOUT = .5
        client.DEFAULT_TIMEOUT_MOVF = 1.
        client.DEFAULT_TIMEOUT_OVF = 1
        self.overflow = client.DEFAULT_TIMEOUT + .5
        self.moverflow = client.DEFAULT_TIMEOUT_MOVF + .5

    def tearDown(self):
        logger.debug('stopping cluster')
        for cl in self.clusters:
            cl.stop()
        for fl in self.files:
            os.remove(fl)
        logger.debug('cluster stopped')
        client.DEFAULT_TIMEOUT = self.old_timeout
        client.DEFAULT_TIMEOUT_MOVF = self.old_movf
        client.DEFAULT_TIMEOUT_OVF = self.old_ovf

    def _get_file(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        self.files.append(path)
        return path

    def _get_cluster(self, callable, **kw):
        logger.debug('getting cluster')
        front = 'ipc:///tmp/f-%s' % callable
        back = 'ipc:///tmp/b-%s' % callable
        hb = 'ipc:///tmp/h-%s' % callable
        reg = 'ipc:///tmp/r-%s' % callable

        cl = get_cluster(callable, frontend=front, backend=back, heartbeat=hb,
                         register=reg,
                         numprocesses=1, background=True, debug=True,
                         timeout=client.DEFAULT_TIMEOUT_MOVF, **kw)
        cl.start()
        time.sleep(1.)  # stabilization
        self.clusters.append(cl)
        logger.debug('cluster ready')
        return client.Pool(size=3, frontend=front, debug=True,
                timeout=client.DEFAULT_TIMEOUT,
                timeout_max_overflow=client.DEFAULT_TIMEOUT_MOVF,
                timeout_overflows=client.DEFAULT_TIMEOUT_OVF)

    def test_error(self):
        client = self._get_cluster('loads.tests.jobs.fail')
        self.assertRaises(ExecutionError, client.execute, {'arg': 'xx'})

    def test_timeout(self):
        client = self._get_cluster('loads.tests.jobs.timeout_overflow')
        self.assertRaises(TimeoutError, client.execute, {'age': self.moverflow})

    def test_success(self):
        client = self._get_cluster('loads.tests.jobs.success')
        self.assertEqual(client.execute({'arg': 'xx'}), 'xx')

    def test_timeout_ovf(self):
        # this should work 1 time then fail
        file = self._get_file()
        client = self._get_cluster('loads.tests.jobs.timeout_overflow',
                                   logfile=file)

        # trying a PING
        time.sleep(.5)
        self.assertTrue(client.ping() is not None)
        ovf = str(self.overflow)
        try:
            res = client.execute({'age': self.overflow})
            self.assertEqual(res, ovf)
        except Exception:
            with open(file) as f:
                raise Exception(f.read())

        try:
            self.assertRaises(TimeoutError, client.execute,
                              {'age': self.overflow})
        except Exception:
            with open(file) as f:
                raise Exception(f.read())

        # calling it back with the right execution time resets the counter
        self.assertEqual(client.execute({'age': .1}), 'xx')
        self.assertEqual(client.execute({'age': self.overflow}), 'xx')
        self.assertRaises(TimeoutError, client.execute, {'age': self.overflow})

    def test_timeout_dump(self):
        file = self._get_file()
        client = self._get_cluster('loads.tests.jobs.timeout_overflow',
                                    logfile=file)

        self.assertRaises(TimeoutError, client.execute,
                          {'age': self.moverflow})
        time.sleep(2.)      # give the worker a chance to dump the stack

        with open(file) as f:
            res = [line.strip() for line in f.readlines() if line.strip()]

        # the worker should be blocked on the sleep
        try:
            self.assertTrue("time.sleep(job.data['age'])" in res)
        except Exception:
            raise AssertionError(res)

    def test_worker_max_age(self):
        # a worker with a max age of 1.5
        client = self._get_cluster('loads.tests.jobs.success',
                                   max_age=1.5, max_age_delta=0)
        time.sleep(.5)

        self.assertEqual(client.execute({'arg': 'xx'}), 'xx')

        cl = self.clusters[-1]

        # get the pid of the current worker
        pid = cl.watchers[1].processes.keys()[0]

        # wait 3 seconds
        time.sleep(3.)

        # should be different
        self.assertNotEqual(pid, cl.watchers[1].processes.keys()[0])

    def test_worker_max_age2(self):

        # we want to run a job, and have the max age reached while the job
        # is being executed, to verify that the job returns before the
        # worker is killed.
        client.DEFAULT_TIMEOUT = 5.
        client.DEFAULT_TIMEOUT_MOVF = 7.
        file = self._get_file()
        _client = self._get_cluster('loads.tests.jobs.timeout_overflow',
                                    max_age=5., max_age_delta=0,
                                    logfile=file)

        time.sleep(.2)
        cl = self.clusters[-1]

        # get the pid of the current worker
        pid = cl.watchers[1].processes.keys()[0]

        # work for 3 seconds
        try:
            self.assertEqual(_client.execute({'age': 6.0}), '6.0')
        except Exception:
            with open(file) as f:
                print(f.read())
            raise

        # wait until the process is dead
        now = time.time()
        while psutil.pid_exists(int(pid)) and time.time() - now < 10.:
            time.sleep(.1)

        # now give a chance to the new one to stabilize
        time.sleep(1.)

        # should be different
        try:
            self.assertNotEqual(pid, cl.watchers[1].processes.keys()[0])
        except Exception:
            with open(file) as f:
                print(f.read())
            raise

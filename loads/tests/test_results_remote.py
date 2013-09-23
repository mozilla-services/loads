from unittest2 import TestCase

from loads.results.remote import RemoteTestResult
from loads.results import remote

import mock


class TestRemoteTestResult(TestCase):

    def setUp(self):
        self._old_client = remote.Client
        remote.Client = mock.MagicMock()
        remote.Client.get_data = mock.MagicMock()

    def tearDown(self):
        remote.Client = self._old_client

    def test_getattributes(self):
        # RemoteTestResult has some magic attribute getters

        remote = RemoteTestResult()
        self.assertRaises(NotImplementedError, getattr, remote, 'errors')

        args = {'agents': [], 'broker': 'tcp://example.com:999'}
        remote = RemoteTestResult(args=args)
        self.assertEqual(list(remote.errors), [])
        self.assertEqual(list(remote.failures), [])

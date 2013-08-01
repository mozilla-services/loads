from unittest import TestCase

from loads.relay import ZMQRelay
from loads.tests.support import get_tb, hush

import mock


class TestZmqRelay(TestCase):

    def setUp(self):
        self._old_init_socket = ZMQRelay._init_socket
        ZMQRelay._init_socket = mock.Mock()
        self.relay = ZMQRelay(args={})
        self.relay.push = mock.Mock()

    def tearDown(self):
        ZMQRelay._init_socket = self._old_init_socket

    def test_add_success(self):
        self.relay.addSuccess(mock.sentinel.test, mock.sentinel.loads_status)
        self.relay.push.assert_called_with(
            'addSuccess',
            test=str(mock.sentinel.test),  # we stringify the test
            loads_status=mock.sentinel.loads_status)
            # loads_status is not transformed

    @hush
    def test_add_failure(self):
        exc = get_tb()
        self.relay.addFailure(mock.sentinel.test, exc,
                              mock.sentinel.loads_status)
        self.relay.push.assert_called_with(
            'addFailure',
            test='sentinel.test',
            exc_info=("<type 'exceptions.Exception'>", '', ''),
            loads_status=mock.sentinel.loads_status)

    @hush
    def test_add_error(self):
        exc = get_tb()
        self.relay.addError(mock.sentinel.test, exc,
                            mock.sentinel.loads_status)
        self.relay.push.assert_called_with(
            'addError',
            test='sentinel.test',
            exc_info=("<type 'exceptions.Exception'>", '', ''),
            loads_status=mock.sentinel.loads_status)

    def test_start_test(self):
        self.relay.startTest(mock.sentinel.test, mock.sentinel.loads_status)
        self.relay.push.assert_called_with(
            'startTest',
            test=str(mock.sentinel.test),
            loads_status=mock.sentinel.loads_status)

    def test_stop_test(self):
        self.relay.stopTest(mock.sentinel.test, mock.sentinel.loads_status)
        self.relay.push.assert_called_with(
            'stopTest',
            test=str(mock.sentinel.test),
            loads_status=mock.sentinel.loads_status)

    def test_start_testrun(self):
        self.relay.startTestRun()
        self.relay.push.assert_called_with('startTestRun')

    def test_stop_testrun(self):
        self.relay.stopTestRun()
        self.relay.push.assert_called_with('stopTestRun')

    def test_socket_open_close(self):
        for action in ('open', 'close'):
            meth = getattr(self.relay, 'socket_%s' % action)
            meth()
            self.relay.push.assert_called_with('socket_%s' % action)

    def test_socket_message_received(self):
        self.relay.socket_message(123)
        self.relay.push.assert_called_with('socket_message', size=123)

    def test_add_hit(self):
        args = {'foo': 'bar', 'baz': 'foobar'}
        self.relay.add_hit(**args)
        self.relay.push.assert_called_with('add_hit', **args)

    def test_add_observer(self):
        # The observer API should silently accept the observers we pass to it,
        # and be future proof
        self.relay.add_observer('foo', bar='baz')

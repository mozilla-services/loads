from unittest import TestCase

from loads.relay import ZMQRelay
from loads.tests.support import get_tb, hush

import mock


class TestZmqRelay(TestCase):

    def setUp(self):
        self.relay = ZMQRelay(args={})
        self.relay.push = mock.Mock()

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

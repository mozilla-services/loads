from unittest2 import TestCase
import traceback
from StringIO import StringIO
import zmq.green as zmq

from loads.results import ZMQTestResult
from loads.tests.support import get_tb, hush
from loads.util import json

import mock


class TestZmqRelay(TestCase):

    def setUp(self):
        self.context = zmq.Context()
        self._pull = self.context.socket(zmq.PULL)
        self._pull.bind('inproc://ok')
        self.relay = ZMQTestResult(args={'zmq_receiver': 'inproc://ok',
                                         'zmq_context': self.context})

    def tearDown(self):
        self.context.destroy()
        self.relay.close()

    def test_add_success(self):
        self.relay.addSuccess(mock.sentinel.test,
                              str(mock.sentinel.loads_status))
        recv = json.loads(self._pull.recv())
        self.assertEqual(recv['loads_status'],
                         str(mock.sentinel.loads_status))
        self.assertEqual(recv['test'],
                         str(mock.sentinel.test))

    @hush
    def test_add_failure(self):
        exc = get_tb()
        __, __, tb = exc
        string_tb = StringIO()
        traceback.print_tb(tb, file=string_tb)
        string_tb.seek(0)

        self.relay.addFailure(mock.sentinel.test, exc,
                              str(mock.sentinel.loads_status))

        recv = json.loads(self._pull.recv())
        self.assertEqual(recv['loads_status'],
                         str(mock.sentinel.loads_status))
        self.assertEqual(recv['test'],
                         str(mock.sentinel.test))
        exc_info = ["<type 'exceptions.Exception'>",
                    'Error message', string_tb.read()]

        self.assertEqual(recv['exc_info'], exc_info)

    @hush
    def test_add_error(self):
        exc = get_tb()
        __, __, tb = exc
        string_tb = StringIO()
        traceback.print_tb(tb, file=string_tb)
        string_tb.seek(0)

        self.relay.addError(mock.sentinel.test, exc,
                            str(mock.sentinel.loads_status))

        recv = json.loads(self._pull.recv())
        self.assertEqual(recv['loads_status'],
                         str(mock.sentinel.loads_status))
        self.assertEqual(recv['test'],
                         str(mock.sentinel.test))
        exc_info = ["<type 'exceptions.Exception'>",
                    'Error message', string_tb.read()]

        self.assertEqual(recv['exc_info'], exc_info)

    def test_start_test(self):
        self.relay.startTest(mock.sentinel.test,
                             str(mock.sentinel.loads_status))
        recv = json.loads(self._pull.recv())
        self.assertEqual(recv['loads_status'],
                         str(mock.sentinel.loads_status))
        self.assertEqual(recv['test'],
                         str(mock.sentinel.test))

    def test_stop_test(self):
        self.relay.stopTest(mock.sentinel.test,
                            str(mock.sentinel.loads_status))
        recv = json.loads(self._pull.recv())
        self.assertEqual(recv['loads_status'],
                         str(mock.sentinel.loads_status))
        self.assertEqual(recv['test'],
                         str(mock.sentinel.test))

    def test_start_testrun(self):
        self.relay.startTestRun()
        recv = json.loads(self._pull.recv())
        self.assertEqual(recv['data_type'], 'startTestRun')

    def test_stop_testrun(self):
        self.relay.stopTestRun()
        recv = json.loads(self._pull.recv())
        self.assertEqual(recv['data_type'], 'stopTestRun')

    def test_socket_open_close(self):
        for action in ('open', 'close'):
            action = 'socket_%s' % action
            meth = getattr(self.relay, action)
            meth()
            recv = json.loads(self._pull.recv())
            self.assertEqual(recv['data_type'], action)

    def test_socket_message_received(self):
        self.relay.socket_message(123)
        recv = self._pull.recv()
        self.assertEqual(json.loads(recv)['size'], 123)

    def test_add_hit(self):
        args = {'foo': 'bar', 'baz': 'foobar'}
        self.relay.add_hit(**args)
        recv = self._pull.recv()
        self.assertDictContainsSubset(args, json.loads(recv))

    def test_incr_counter(self):
        args = 'test', (1, 1, 1, 1), 'metric'
        self.relay.incr_counter(*args)
        wanted = {'test': 'test', 'loads_status': [1, 1, 1, 1],
                  'agent_id': None}

        recv = self._pull.recv()
        self.assertDictContainsSubset(wanted, json.loads(recv))

    def test_add_observer(self):
        # The observer API should silently accept the observers we pass to it,
        # and be future proof
        self.relay.add_observer('foo', bar='baz')

    def test_error(self):
        self.context.destroy()
        args = {'foo': 'bar', 'baz': 'foobar'}
        self.assertRaises(zmq.ZMQError, self.relay.add_hit, **args)

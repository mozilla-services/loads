import StringIO
import datetime
import mock
import sys
import unittest

from loads.output.std import StdOutput
from loads.output import create_output, output_list, register_output


class FakeTestResult(object):
    def __init__(self):
        self.nb_hits = 10
        self.start_time = datetime.datetime.now()
        self.duration = 0
        self.average_request_time = lambda: 0
        self.sockets = 0
        self.socket_data_received = 0
        self.nb_success = self.nb_errors = self.nb_failures = 0
        self.nb_finished_tests = 0


class FakeOutput(object):
    name = 'fake'
    options = {'arg1': ('Some doc', str, None, False)}

    def __init__(self, test_result, args):
        self.args = args
        self.test_result = test_result


class TestStdOutput(unittest.TestCase):

    def test_std(self):
        old = sys.stdout
        sys.stdout = StringIO.StringIO()

        test_result = FakeTestResult()
        try:
            std = StdOutput(test_result, {'total': 10})
            for i in range(11):
                test_result.nb_finished_tests += 1
                std.push('stopTest')
            std.flush()
        finally:
            sys.stdout.seek(0)
            output = sys.stdout.read()
            sys.stdout = old

        self.assertTrue('Hits: 10' in output)
        self.assertTrue('100%' in output)


class TestOutputPlugins(unittest.TestCase):

    def test_unexistant_output_raises_exception(self):
        self.assertRaises(NotImplementedError, create_output, 'xxx', None,
                          None)

    @mock.patch('loads.output._OUTPUTS', {})
    def test_register_item_works(self):
        register_output(FakeOutput)
        self.assertTrue(FakeOutput in output_list())

    @mock.patch('loads.output._OUTPUTS', {})
    def test_register_multiple_times(self):
        register_output(FakeOutput)
        register_output(FakeOutput)
        self.assertTrue(FakeOutput in output_list())
        self.assertEquals(len(output_list()), 1)

    @mock.patch('loads.output._OUTPUTS', {})
    def test_create_output(self):
        register_output(FakeOutput)
        obj = create_output('fake', mock.sentinel.test_result,
                            mock.sentinel.args)
        self.assertEquals(obj.args, mock.sentinel.args)
        self.assertEquals(obj.test_result, mock.sentinel.test_result)

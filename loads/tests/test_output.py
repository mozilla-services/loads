import StringIO
import datetime
import mock
import shutil
import sys
import tempfile
import unittest

from loads.output import (create_output, output_list, register_output,
                          StdOutput, NullOutput, FileOutput)
from loads import output

from loads.tests.support import get_tb, hush


class FakeTestResult(object):
    def __init__(self, nb_errors=0, nb_failures=0):
        self.nb_hits = 10
        self.start_time = datetime.datetime.now()
        self.duration = 0
        self.average_request_time = lambda: 0
        self.requests_per_second = lambda: 0
        self.sockets = 0
        self.socket_data_received = 0
        self.nb_success = 0
        self.nb_errors = nb_errors
        self.nb_failures = nb_failures
        self.nb_finished_tests = 0
        self.errors = []
        self.failures = []


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
            out = sys.stdout.read()
            sys.stdout = old

        self.assertTrue('Hits: 10' in out)
        self.assertTrue('100%' in out, out)

    @hush
    def test_errors_are_processed(self):
        test_result = FakeTestResult(nb_errors=1, nb_failures=1)
        std = StdOutput(test_result, {'total': 10})
        std._print_tb = mock.Mock()
        std.flush()
        self.assertEquals(2, std._print_tb.call_count)

    def test_tb_is_rendered(self):
        old = sys.stderr
        sys.stderr = StringIO.StringIO()

        errors = iter([[get_tb(), ]])
        std = StdOutput(mock.sentinel.test_result, mock.sentinel.args)
        std._print_tb(errors)
        sys.stderr.seek(0)
        out = sys.stderr.read()
        sys.stderr = old

        self.assertTrue('Exception' in out)

    def test_empty_tb_is_not_processed(self):
        std = StdOutput(mock.sentinel.test_result, mock.sentinel.args)
        std._print_tb(iter(([], [])))

    def test_classnames_strings_are_used_when_available(self):
        old = sys.stderr
        sys.stderr = StringIO.StringIO()
        std = StdOutput(mock.sentinel.test_result, mock.sentinel.args)
        std._print_tb(iter([[['foo', 'foobar', None]]]))
        sys.stderr.seek(0)
        out = sys.stderr.read()
        sys.stderr = old
        self.assertTrue('foo: foobar' in out)

    def test_relative_value(self):
        self.assertEquals(output.std.get_screen_relative_value(23, 80), 10)


class TestNullOutput(unittest.TestCase):

    def test_api_works(self):
        output = NullOutput(mock.sentinel.test_result, mock.sentinel.args)
        output.push('something')
        output.flush()


class TestFileOutput(unittest.TestCase):

    def test_file_is_written(self):
        tmpdir = tempfile.mkdtemp()
        try:
            output = FileOutput(mock.sentinel.test_result,
                                {'output_file_filename': '%s/loads' % tmpdir})
            output.push('something')
            output.flush()

            with open('%s/loads' % tmpdir) as f:
                self.assertEquals('something - {}', f.read())

        finally:
            shutil.rmtree(tmpdir)


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

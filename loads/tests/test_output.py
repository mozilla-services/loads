import StringIO
import datetime
import mock
import shutil
import sys
import tempfile

from unittest2 import TestCase
from mock import patch

from loads.output import (create_output, output_list, register_output,
                          StdOutput, NullOutput, FileOutput,
                          FunkloadOutput)
from loads import output

from loads.tests.support import get_tb, hush


TIME1 = datetime.datetime(2013, 5, 14, 0, 51, 8)
_1 = datetime.timedelta(seconds=1)


class FakeTestResult(object):
    def __init__(self, nb_errors=0, nb_failures=0):
        self.nb_hits = 10
        self.start_time = datetime.datetime.now()
        self.duration = 0
        self.average_request_time = lambda: 0
        self.requests_per_second = lambda: 0
        self.opened_sockets = 0
        self.socket_data_received = 0
        self.nb_success = 0
        self.nb_errors = nb_errors
        self.nb_failures = nb_failures
        self.nb_finished_tests = 0
        self.errors = []
        self.failures = []
        self.hits = []
        self.tests = {}

    def get_url_metrics(self):
        return {'http://foo': {'average_request_time': 1.234,
                               'hits_success_rate': 23.},
                'http://baz': {'average_request_time': 12.34,
                               'hits_success_rate': 2.}}

    def get_counters(self):
        return {'boo': 123}


class FakeOutput(object):
    name = 'fake'
    options = {'arg1': ('Some doc', str, None, False)}

    def __init__(self, test_result, args):
        self.args = args
        self.test_result = test_result


class TestStdOutput(TestCase):

    def setUp(self):
        super(TestStdOutput, self).setUp()
        self.oldstdout = sys.stdout
        self.oldstderr = sys.stdout

    def tearDown(self):
        sys.stdout = self.oldstdout
        sys.stderr = self.oldstderr
        super(TestStdOutput, self).tearDown()

    def test_std(self):
        sys.stdout = StringIO.StringIO()

        test_result = FakeTestResult()
        std = StdOutput(test_result, {'total': 10})
        for i in range(11):
            test_result.nb_finished_tests += 1
            std.push('stopTest')
        std.flush()
        sys.stdout.seek(0)
        out = sys.stdout.read()
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
        sys.stderr = StringIO.StringIO()
        errors = iter([[get_tb(), ]])
        std = StdOutput(mock.sentinel.test_result, mock.sentinel.args)
        std._print_tb(errors)
        sys.stderr.seek(0)
        out = sys.stderr.read()
        self.assertTrue('Exception' in out)
        self.assertTrue('Error message' in out)

    def test_empty_tb_is_not_processed(self):
        std = StdOutput(mock.sentinel.test_result, mock.sentinel.args)
        std._print_tb(iter(([], [])))

    def test_classnames_strings_are_used_when_available(self):
        sys.stderr = StringIO.StringIO()
        std = StdOutput(mock.sentinel.test_result, mock.sentinel.args)
        std._print_tb(iter([[['foo', 'foobar', None]]]))
        sys.stderr.seek(0)
        out = sys.stderr.read()
        self.assertTrue('foo: foobar' in out)

    def test_relative_value(self):
        self.assertEquals(output.std.get_screen_relative_value(23, 80), 10)

    def test_url_output(self):
        sys.stdout = StringIO.StringIO()
        test_result = FakeTestResult()
        std = StdOutput(test_result, {'total': 10})
        for i in range(11):
            test_result.nb_finished_tests += 1
            std.push('stopTest')
        std.flush()
        sys.stdout.seek(0)
        out = sys.stdout.read()
        wanted = ['http://baz', 'Average request time: 12.34',
                  'Hits success rate: 2.0', 'http://foo',
                  'Average request time: 1.234',
                  'Hits success rate: 23.0']
        for item in wanted:
            self.assertTrue(item in out)

    def test_counter(self):
        sys.stdout = StringIO.StringIO()
        test_result = FakeTestResult()
        std = StdOutput(test_result, {'total': 10})
        for i in range(11):
            test_result.nb_finished_tests += 1
            std.push('stopTest')
        std.flush()
        sys.stdout.seek(0)
        out = sys.stdout.read()
        wanted = ['boo', '123']
        for item in wanted:
            self.assertTrue(item in out)


class TestNullOutput(TestCase):

    def test_api_works(self):
        output = NullOutput(mock.sentinel.test_result, mock.sentinel.args)
        output.push('something')
        output.flush()


class TestFileOutput(TestCase):

    def test_file_is_written(self):
        tmpdir = tempfile.mkdtemp()
        try:
            output = FileOutput(mock.sentinel.test_result,
                                {'output_file_filename': '%s/loads' % tmpdir})
            output.push('something', 1, 2, method='GET')
            output.flush()

            with open('%s/loads' % tmpdir) as f:
                self.assertEquals('something - {"method": "GET"}', f.read())

        finally:
            shutil.rmtree(tmpdir)


class FakeTestCase(object):
    def __init__(self, name):
        self._testMethodName = name


class TestFunkloadOutput(TestCase):

    @patch('loads.output._funkload.format_tb', lambda x: x)
    def test_file_is_written(self):

        # Create a fake test result object
        test_result = FakeTestResult()

        tmpdir = tempfile.mkdtemp()
        try:
            output = FunkloadOutput(
                test_result,
                {'output_funkload_filename': '%s/funkload.xml' % tmpdir,
                 'fqn': 'my_test_module.MyTestCase.test_mytest',
                 'hits': 200, 'users': [1, 2, 5], 'duration': '1'})

            # Drive the observer with some tests and hits
            output.push('startTestRun', when=TIME1)

            test_case, state = FakeTestCase('test_mytest_foo'), [1, 2, 3, 4]
            output.push('startTest', test_case, state)
            output.push('add_hit', state, started=TIME1, elapsed=_1,
                        url='http://example.local/foo', method='GET',
                        status=200)
            output.push('addSuccess', test_case, state)
            output.push('stopTest', test_case, state)

            test_case, state = FakeTestCase('test_mytest_bar'), [1, 2, 3, 4]
            output.push('startTest', test_case, state)
            output.push('add_hit', state, started=TIME1, elapsed=_1,
                        url='http://example.local/bar', method='GET',
                        status=500)
            output.push(
                'addFailure', test_case, (
                    Exception, Exception('Mock Exception'),
                    ['mock', 'traceback']),
                state)
            output.push('stopTest', test_case, [1, 2, 3, 4])

            output.flush()

            with open('%s/funkload.xml' % tmpdir) as f:
                content = f.read()
                test = (
                    '<response\n    cycle="001" cvus="002" thread="004" '
                    'suite="" name=""\n    step="001" number="001" '
                    'type="get" result="Successful" '
                    'url="http://example.local/foo"\n    code="200" '
                    'description="" time="1368492668" duration="1.0" />',)
                for t in test:
                    self.assertIn(t, content)

                test = (
                    '<testResult\n    cycle="001" cvus="002" thread="004" '
                    'suite="FakeTestCase"\n    name="test_mytest_foo" ',
                    'result="Successful" steps="1"\n',
                    'connection_duration="0" requests="1"\n    pages="1" '
                    'xmlrpc="0" redirects="0" images="0" links="0"\n    />')
                for t in test:
                    self.assertIn(t, content)

                test = (
                    '<response\n    cycle="001" cvus="002" thread="004" '
                    'suite="" name=""\n    step="001" number="001" '
                    'type="get" result="Successful" '
                    'url="http://example.local/bar"\n    code="500" '
                    'description="" time="1368492668" duration="1.0" />',)
                for t in test:
                    self.assertIn(t, content)

                test = (
                    '<testResult\n    cycle="001" cvus="002" thread="004" '
                    'suite="FakeTestCase"\n    name="test_mytest_foo" ',
                    'result="Failure" steps="1"\n',
                    'connection_duration="0" requests="1"\n    pages="1" '
                    'xmlrpc="0" redirects="0" images="0" links="0"\n'
                    '    traceback="mock&#10;traceback"/>')
                for t in test:
                    self.assertIn(t, content)

        finally:
            shutil.rmtree(tmpdir)


class TestOutputPlugins(TestCase):

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

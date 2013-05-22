import unittest
import datetime
import sys
import StringIO

from loads.output.std import StdOutput
from loads.output import create_output, output_list


class FakeTestResult(object):
    def __init__(self):
        self.nb_hits = 10
        self.start_time = datetime.datetime.now()
        self.duration = 0
        self.average_request_time = 0
        self.sockets = 0
        self.socket_data_received = 0


class TestStdOutput(unittest.TestCase):

    def test_std(self):
        old = sys.stdout
        sys.stdout = StringIO.StringIO()

        test_result = FakeTestResult()
        try:
            std = StdOutput(test_result, {'total': 10})
            for i in range(11):
                std.push('add_hit', current=i)
            std.flush()
        finally:
            sys.stdout.seek(0)
            output = sys.stdout.read()
            sys.stdout = old

        print output
        self.assertTrue('Hits: 10' in output)
        self.assertTrue('100%' in output)

    def test_global(self):
        self.assertRaises(NotImplementedError, create_output, 'xxx', None,
                          None)

        #  XXX We should mock that out in the tests.
        wanted = ['null', 'file', 'stdout', ]
        wanted.sort()
        got = [st.name for st in output_list()]
        got.sort()
        self.assertEqual(got, wanted)

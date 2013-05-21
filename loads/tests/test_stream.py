import unittest
import datetime
import sys
import StringIO

from loads.output.std import StdOutput
from loads.output import create_output, output_list


class TestStdOutput(unittest.TestCase):

    def test_std(self):
        old = sys.stdout
        sys.stdout = StringIO.StringIO()

        try:
            std = StdOutput({'total': 10})

            for i in range(10):
                data = {'started': datetime.datetime.now()}
                std.push('hit', data)

            std.flush()
        finally:
            sys.stdout.seek(0)
            output = sys.stdout.read()
            sys.stdout = old

        self.assertTrue('Hits: 10' in output)
        self.assertTrue('100%' in output)

    def test_global(self):
        self.assertRaises(NotImplementedError, create_output, 'xxx', None)

        #  XXX We should mock that out in the tests.
        wanted = ['null', 'file', 'stdout', ]
        wanted.sort()
        got = [st.name for st in output_list()]
        got.sort()
        self.assertEqual(got, wanted)

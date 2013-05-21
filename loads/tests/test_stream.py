import unittest
import datetime
import sys
import StringIO

from loads.stream.std import StdStream
from loads.stream import create_stream, stream_list


class TestStdStream(unittest.TestCase):

    def test_std(self):
        old = sys.stdout
        sys.stdout = StringIO.StringIO()

        try:
            std = StdStream({'total': 10})

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
        self.assertRaises(NotImplementedError, create_stream, 'xxx', None)

        wanted = ['zmq', 'null', 'file', 'stdout', 'collector']
        wanted.sort()
        got = [st.name for st in stream_list()]
        got.sort()
        self.assertEqual(got, wanted)

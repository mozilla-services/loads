import unittest
import datetime
import sys
import StringIO

from loads.stream.std import StdStream
from loads.stream import set_global_stream, stream_list


class TestStdStream(unittest.TestCase):

    def test_std(self):
        old = sys.stdout
        sys.stdout = StringIO.StringIO()

        try:
            std = StdStream({'stream_stdout_total': 10})

            for i in range(10):
                data = {'started': datetime.datetime.now()}
                std.push(data)

            std.flush()
        finally:
            sys.stdout.seek(0)
            output = sys.stdout.read()
            sys.stdout = old

        self.assertTrue('Hits: 10' in output)
        self.assertTrue('100%' in output)

    def test_global(self):
        self.assertRaises(NotImplementedError, set_global_stream, 'xxx', None)

        wanted = ['zmq', 'null', 'file', 'stdout']
        wanted.sort()
        got = [st.name for st in stream_list()]
        got.sort()
        self.assertEqual(got, wanted)

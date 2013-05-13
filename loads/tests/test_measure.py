import unittest

from loads.measure import Session
from loads import measure
from loads.stream import set_global_stream, get_global_stream, register_stream

from requests.adapters import HTTPAdapter


class _FakeTest(object):
    pass


class _FakeResponse(object):
    elapsed = 1
    cookies = {}
    headers = {}
    status_code = 200
    url = 'http://impossible.place'


class _Stream(object):
    name = 'test'

    def __init__(self, args):
        self.stream = []

    def push(self, data):
        self.stream.append(data)


register_stream(_Stream)


class TestMeasure(unittest.TestCase):

    def setUp(self):
        self.old_dns = measure.dns_resolve
        self.old_send = HTTPAdapter.send
        HTTPAdapter.send = self._send
        measure.dns_resolve = self._dns
        self.old_stream = get_global_stream()

    def tearDown(self):
        measure.dns_resolve = self.old_dns
        HTTPAdapter.send = self.old_send
        if self.old_stream is not None:
            set_global_stream(self.old_stream.name,
                              self.old_stream.args)

    def _send(self, *args, **kw):
        return _FakeResponse()

    def _dns(self, url):
        return url, url, 'meh'

    def test_session(self):
        set_global_stream('test', None)
        test = _FakeTest()
        session = Session(test)
        session.get('http://impossible.place')
        stream = get_global_stream()
        self.assertEqual(len(stream.stream), 1)

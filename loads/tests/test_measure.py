import unittest

from loads.measure import Session
from loads import measure
from loads.stream import create_stream, register_stream, _STREAMS

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

    def push(self, data_type, data):
        self.stream.append(data)


class TestMeasure(unittest.TestCase):

    def setUp(self):
        self.old_dns = measure.dns_resolve
        self.old_send = HTTPAdapter.send
        HTTPAdapter.send = self._send
        measure.dns_resolve = self._dns
        self.old_streams = dict(_STREAMS)

    def tearDown(self):
        measure.dns_resolve = self.old_dns
        HTTPAdapter.send = self.old_send
        _STREAMS.clear()
        _STREAMS.update(self.old_streams)

    def _send(self, *args, **kw):
        return _FakeResponse()

    def _dns(self, url):
        return url, url, 'meh'

    def test_session(self):
        register_stream(_Stream)
        stream = create_stream('test', None)
        test = _FakeTest()
        session = Session(test, stream)
        session.get('http://impossible.place')
        self.assertEqual(len(stream.stream), 1)

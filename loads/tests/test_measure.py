import unittest
import functools

from loads.measure import Session
from loads import measure

from requests.adapters import HTTPAdapter


class _FakeTest(object):
    pass


class _FakeResponse(object):
    elapsed = 1
    cookies = {}
    headers = {}
    status_code = 200
    url = 'http://impossible.place'


class _TestResult(object):

    def __init__(self):
        self.data = []

    def __getattr__(self, name):
        # Relay all the methods to the self.push method if they are part of the
        # protocol.
        if name in ('startTest', 'stopTest', 'addFailure', 'addError',
                    'addSuccess', 'add_hit'):  # XXX change to camel_case
            return functools.partial(self.push, data_type=name)

    def push(self, data_type, **data):
        self.data.append(data)


class TestMeasure(unittest.TestCase):

    def setUp(self):
        self.old_dns = measure.dns_resolve
        self.old_send = HTTPAdapter.send
        HTTPAdapter.send = self._send
        measure.dns_resolve = self._dns

    def tearDown(self):
        measure.dns_resolve = self.old_dns
        HTTPAdapter.send = self.old_send

    def _send(self, *args, **kw):
        return _FakeResponse()

    def _dns(self, url):
        return url, url, 'meh'

    def test_session(self):
        test = _FakeTest()
        test_result = _TestResult()
        session = Session(test, test_result)
        session.get('http://impossible.place')
        self.assertEqual(len(test_result.data), 1)

import unittest2
import functools
import mock

from loads.measure import Session
from loads import measure
from loads.tests.support import hush

from requests.adapters import HTTPAdapter


# XXX replace my Mock
class _FakeTest(object):
    pass


class _Headers(object):
    def getheaders(self, name):
        return {}


class _Original(object):
    msg = _Headers()


class _Response(object):
    _original_response = _Original()


class _FakeResponse(object):
    history = False
    elapsed = 1
    cookies = {}
    headers = {}
    status_code = 200
    url = 'http://impossible.place'
    raw = _Response()


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


class TestMeasure(unittest2.TestCase):

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

    @hush
    def test_session(self):
        test = _FakeTest()
        test_result = _TestResult()
        session = Session(test, test_result)
        session.get('http://impossible.place')
        self.assertEqual(len(test_result.data), 1)

    def test_host_proxy(self):
        uri = 'https://super-server:443/'
        proxy = measure.HostProxy(uri)
        self.assertEquals(proxy.uri, 'https://super-server:443')
        env = {}
        self.assertEquals(proxy.extract_uri(env), 'https://super-server:443')
        self.assertEquals(env['HTTP_HOST'], 'super-server:443')
        self.assertEquals(proxy.scheme, 'https')

        proxy.uri = 'http://somewhere-else'
        self.assertEquals(proxy.extract_uri(env), 'http://somewhere-else')
        self.assertEquals(env['HTTP_HOST'], 'somewhere-else')
        self.assertEquals(proxy.scheme, 'http')

    def test_TestApp(self):
        session = mock.sentinel.session
        test_result = _TestResult()

        app = measure.TestApp('http://super-server', session, test_result)
        self.assertEquals(app.server_url, 'http://super-server')

        app.server_url = 'http://somewhere-else'
        self.assertEquals(app.server_url, 'http://somewhere-else')

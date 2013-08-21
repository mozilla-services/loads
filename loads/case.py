import unittest

from requests.adapters import HTTPAdapter

from loads.measure import Session, TestApp
from loads.results import LoadsTestResult, UnitTestTestResult


class FakeTestApp(object):

    def __getattr__(self, arg):
        def wrapper(*args, **kwargs):
            raise ValueError(('If you want to use the webtest.TestApp client, '
                              'you need to add a "server_url" property to '
                              'your TestCase or call loads with the '
                              '--server-url option'))
        return wrapper


MAX_CON = 1000


class TestCase(unittest.TestCase):

    server_url = None

    def __init__(self, test_name, test_result=None, config=None):
        super(TestCase, self).__init__(test_name)
        if config is None:
            config = {}
        self.config = config
        if config.get('server_url') is not None:
            self.server_url = config['server_url']
        self._test_result = test_result

        self.session = Session(test=self, test_result=test_result)
        http_adapter = HTTPAdapter(pool_maxsize=MAX_CON,
                                   pool_connections=MAX_CON)
        self.session.mount('http://', http_adapter)
        self.session.mount('https://', http_adapter)

        if self.server_url is not None:
            self.app = TestApp(self.server_url, self.session, test_result)
        else:
            self.app = FakeTestApp()

        self._ws = []
        self._loads_status = None

    def defaultTestResult(self):
        return LoadsTestResult()

    def incr_counter(self, name):
        self._test_result.incr_counter(self, self._loads_status, name)

    def create_ws(self, url, callback=None, protocols=None, extensions=None,
                  klass=None):
        from loads.websockets import create_ws
        ws = create_ws(url, self._test_result,
                       callback=callback,
                       protocols=protocols,
                       extensions=extensions,
                       klass=klass,
                       test_case=self)
        self._ws.append(ws)
        return ws

    def tearDown(self):
        for ws in self._ws:
            if ws._th.dead:
                ws._th.get()  # re-raise any exception swallowed by gevent

    def run(self, result=None, loads_status=None):
        if (loads_status is not None
                and result is None
                and not isinstance(self._test_result, LoadsTestResult)):
            result = LoadsTestResult(loads_status, self._test_result)

        if loads_status is not None:
            self._loads_status = self.session.loads_status = loads_status

        return super(TestCase, self).run(result)


def _patching():
    # patching nose if present
    try:
        from nose import core
        core._oldTextTestResult = core.TextTestResult

        class _TestResult(core._oldTextTestResult):
            def startTest(self, test, *args, **kw):
                super(_TestResult, self).startTest(test)

            def stopTest(self, test, *args, **kw):
                super(_TestResult, self).stopTest(test)

            def addError(self, test, exc_info, *args, **kw):
                super(_TestResult, self).addError(test, exc_info)

            def addFailure(self, test, exc_info, *args, **kw):
                super(_TestResult, self).addFailure(test, exc_info)

            def addSuccess(self, test, *args, **kw):
                super(_TestResult, self).addSuccess(test)

        core.TextTestResult = _TestResult

        from nose import proxy
        proxy._ResultProxy = proxy.ResultProxy

        class _ResultProxy(proxy._ResultProxy):
            def startTest(self, test, *args, **kw):
                super(_ResultProxy, self).startTest(test)

            def stopTest(self, test, *args, **kw):
                super(_ResultProxy, self).stopTest(test)

            def addError(self, test, exc_info, *args, **kw):
                super(_ResultProxy, self).addError(test, exc_info)

            def addFailure(self, test, exc_info, *args, **kw):
                super(_ResultProxy, self).addFailure(test, exc_info)

            def addSuccess(self, test, *args, **kw):
                super(_ResultProxy, self).addSuccess(test)

        proxy.ResultProxy = _ResultProxy
    except ImportError:
        pass

    # patch unittest TestResult object
    try:
        import unittest2.runner
        unittest2.runner.TextTestResult = UnitTestTestResult
    except ImportError:
        pass


_patching()

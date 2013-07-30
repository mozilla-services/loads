import unittest
import functools

from requests.adapters import HTTPAdapter
from loads.measure import Session, TestApp


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

    def defaultTestResult(self):
        return TestResult()

    def create_ws(self, url, callback=None, protocols=None, extensions=None,
                  klass=None):
        from loads.websockets import create_ws
        ws = create_ws(url, self._test_result,
                       callback=callback,
                       protocols=protocols,
                       extensions=extensions,
                       klass=klass)
        self._ws.append(ws)
        return ws

    def tearDown(self):
        for ws in self._ws:
            if ws._th.dead:
                ws._th.get()  # re-raise any exception swallowed

    def run(self, result=None, loads_status=None):
        if (loads_status is not None
                and result is None
                and not isinstance(self._test_result, TestResultProxy)):
            result = TestResultProxy(loads_status, self._test_result)

        if loads_status is not None:
            self.session.loads_status = loads_status

        return super(TestCase, self).run(result)


class TestResultProxy(object):

    def __init__(self, loads_status, result):
        self.result = result
        self.loads_status = loads_status

    def __getattribute__(self, name):
        result = super(TestResultProxy, self).__getattribute__('result')
        attr = getattr(result, name)
        if name in ('startTest', 'stopTest', 'addSuccess', 'addException',
                    'addError', 'addFailure'):
            status = (super(TestResultProxy, self).
                      __getattribute__('loads_status'))
            return functools.partial(attr, loads_status=status)
        return attr


class TestResult(unittest.TestResult):
    def startTest(self, test, *args, **kw):
        unittest.TestResult.startTest(self, test)

    def stopTest(self, test, *args, **kw):
        unittest.TestResult.stopTest(self, test)

    def addError(self, test, exc_info, *args, **kw):
        unittest.TestResult.addError(self, test, exc_info)

    def addFailure(self, test, exc_info, *args, **kw):
        unittest.TestResult.addFailure(self, test, exc_info)

    def addSuccess(self, test, *args, **kw):
        unittest.TestResult.addSuccess(self, test)


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
        unittest2.runner.TextTestResult = TestResult
    except ImportError:
        pass


_patching()

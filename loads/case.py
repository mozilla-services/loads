import unittest
import sys
import warnings
from unittest import SkipTest
from unittest.case import _ExpectedFailure, _UnexpectedSuccess

from loads.measure import Session, TestApp
from loads.websockets import create_ws


class FakeTestApp(object):

    def __getattr__(self, arg):
        def wrapper(*args, **kwargs):
            raise ValueError(('If you want to use the webtest.TestApp client, '
                              'you need to add a "server_url" property to '
                              'your TestCase or call loads with the '
                              '--server-url option'))
        return wrapper


class TestCase(unittest.TestCase):
    def __init__(self, test_name, test_result=None, server_url=None):
        super(TestCase, self).__init__(test_name)
        self.server_url = server_url or getattr(self, 'server_url', None)
        self._test_result = test_result

        self.session = Session(test=self, test_result=test_result)
        if self.server_url is not None:
            self.app = TestApp(self.server_url, self.session, test_result)
        else:
            self.app = FakeTestApp()

    def defaultTestResult(self):
        return TestResult()

    def create_ws(self, url, callback, protocols=None, extensions=None):
        return create_ws(url, callback, self._test_result, protocols,
                         extensions)

    def run(self, result=None, cycle=-1, user=-1, current_cycle=-1,
            current_user=-1):
        # pass the information about the cycles to the session so we're able to
        # track which cycle the information sent belongs to, if there is any.
        loads_status = (cycle, user, current_cycle, current_user)
        self.session.loads_status = loads_status

        # We want to be compatible with the unittest / nose APIs, so we need to
        # be sure to get back the TestResult object is the good one
        # If nothing is passed to the method, it means we should get the info
        # from the class, and that we are in the context of a loads run
        if result is None:
            result = self._test_result

        orig_result = result

        if result is None:
            result = self.defaultTestResult()
            startTestRun = getattr(result, 'startTestRun', None)
            if startTestRun is not None:
                startTestRun()

        self._resultForDoCleanups = result
        result.startTest(self, loads_status)

        testMethod = getattr(self, self._testMethodName)
        if (getattr(self.__class__, "__unittest_skip__", False) or   # NOQA
            getattr(testMethod, "__unittest_skip__", False)):
            # If the class or method was skipped.
            try:
                skip_why = (getattr(self.__class__,
                            '__unittest_skip_why__', '')
                            or getattr(testMethod,
                                       '__unittest_skip_why__', ''))
                self._addSkip(result, skip_why)
            finally:
                result.stopTest(self, loads_status)
            return
        try:
            success = False
            try:
                self.setUp()
            except SkipTest as e:
                self._addSkip(result, str(e))
            except Exception:
                result.addError(self, sys.exc_info(), loads_status)
            else:
                try:
                    testMethod()
                except self.failureException:
                    result.addFailure(self, sys.exc_info(), loads_status)
                except _ExpectedFailure as e:
                    addExpectedFailure = getattr(result,
                                                 'addExpectedFailure',
                                                 None)
                    if addExpectedFailure is not None:
                        addExpectedFailure(self, e.exc_info)
                    else:
                        warnings.warn("TestResult has no addExpectedFailure"
                                      " method, reporting as passes",
                                      RuntimeWarning)
                        result.addSuccess(self, loads_status)
                except _UnexpectedSuccess:
                    addUnexpectedSuccess = getattr(result,
                                                   'addUnexpectedSuccess',
                                                   None)
                    if addUnexpectedSuccess is not None:
                        addUnexpectedSuccess(self)
                    else:
                        warnings.warn("TestResult has no addUnexpectedSuccess "
                                      "method, reporting as failures",
                                      RuntimeWarning)
                        result.addFailure(self, sys.exc_info(), loads_status)
                except SkipTest as e:
                    self._addSkip(result, str(e))
                except Exception:
                    result.addError(self, sys.exc_info(), loads_status)
                else:
                    success = True

                try:
                    self.tearDown()
                except Exception:
                    result.addError(self, sys.exc_info())
                    success = False

            cleanUpSuccess = self.doCleanups()
            success = success and cleanUpSuccess
            if success:
                result.addSuccess(self, loads_status)
        finally:
            result.stopTest(self, loads_status)

            if orig_result is None:
                stopTestRun = getattr(result, 'stopTestRun', None)
                if stopTestRun is not None:
                    stopTestRun()


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

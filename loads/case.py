import unittest
import sys
import warnings
from unittest import SkipTest
from unittest.case import _ExpectedFailure, _UnexpectedSuccess

from loads.measure import Session


class TestCase(unittest.TestCase):
    def __init__(self, test_name):
        super(TestCase, self).__init__(test_name)
        self.session = Session(self)

    def create_ws(self, url, callback, protocols=None, extensions=None):
        from loads.websockets import create_ws
        return create_ws(url, callback, protocols, extensions)

    def run(self, result, cycle=-1, user=-1, current_cycle=-1):
        orig_result = result
        if result is None:
            result = self.defaultTestResult()
            startTestRun = getattr(result, 'startTestRun', None)
            if startTestRun is not None:
                startTestRun()

        self._resultForDoCleanups = result
        result.startTest(self, cycle, user, current_cycle)

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
                result.stopTest(self, cycle, user, current_cycle)
            return
        try:
            success = False
            try:
                self.setUp()
            except SkipTest as e:
                self._addSkip(result, str(e))
            except Exception:
                result.addError(self, sys.exc_info(), cycle, user,
                                current_cycle)
            else:
                try:
                    testMethod()
                except self.failureException:
                    result.addFailure(self, sys.exc_info())
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
                        result.addSuccess(self, cycle, user, current_cycle)
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
                        result.addFailure(self, sys.exc_info(), cycle, user,
                                          current_cycle)
                except SkipTest as e:
                    self._addSkip(result, str(e))
                except Exception:
                    result.addError(self, sys.exc_info(), cycle, user,
                                    current_cycle)
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
                result.addSuccess(self, cycle, user, current_cycle)
        finally:
            result.stopTest(self, cycle, user, current_cycle)
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

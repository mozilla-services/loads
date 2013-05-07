import unittest
import sys
import warnings
from unittest import SkipTest
from unittest.case import _ExpectedFailure, _UnexpectedSuccess

from loads import _patch  # NOQA

__version__ = '0.1'


class TestCase(unittest.TestCase):
    def __init__(self, test_name):
        from loads.measure import Session
        unittest.TestCase.__init__(self, test_name)
        self.session = Session(self)

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

import unittest


class UnitTestTestResult(unittest.TestResult):
    """Used to make Loads test cases compatible with unittest

    This class will ignore the extra options used by Loads, so
    tests written for loads can also be run in Nose or Unittest(2)
    """
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

    def incr_counter(self, test, *args, **kw):
        pass

import unittest2
import mock

from loads.case import TestCase
from loads.results import UnitTestTestResult


class _MyTestCase(TestCase):
    def test_one(self):
        self.incr_counter('meh')

    def test_two(self):
        raise AttributeError()

    def test_three(self):
        self.assertTrue(False)


class TestTestCase(unittest2.TestCase):

    def test_fake(self):
        results = UnitTestTestResult()
        loads_status = 1, 1, 1, 1

        case = _MyTestCase('test_one', test_result=results)
        case(loads_status=loads_status)
        self.assertEqual(results.testsRun, 1)
        self.assertEqual(results.wasSuccessful(), True)
        self.assertEqual(len(results.errors), 0)

        case = _MyTestCase('test_two', test_result=results)
        case(loads_status=loads_status)
        self.assertEqual(results.testsRun, 2)
        self.assertEqual(results.wasSuccessful(), False)
        self.assertEqual(len(results.errors), 1)

        case = _MyTestCase('test_three', test_result=results)
        case(loads_status=loads_status)
        self.assertEqual(results.testsRun, 3)
        self.assertEqual(results.wasSuccessful(), False)
        self.assertEqual(len(results.errors), 1)

        self.assertRaises(ValueError, case.app.get, 'boh')

    def test_config_is_passed(self):
        test = _MyTestCase('test_one', test_result=mock.sentinel.results,
                           config={})
        self.assertEquals(test.config, {})

    def test_serverurl_is_overwrited(self):
        _MyTestCase.server_url = 'http://example.org'
        try:
            test = _MyTestCase('test_one', test_result=mock.sentinel.results,
                               config={'server_url': 'http://notmyidea.org'})
            self.assertEquals(test.server_url, 'http://notmyidea.org')
        finally:
            del _MyTestCase.server_url

    def test_serverurl_is_not_overwrited_by_none(self):
        _MyTestCase.server_url = 'http://example.org'
        try:
            test = _MyTestCase('test_one', test_result=mock.sentinel.results,
                               config={'server_url': None})
            self.assertEquals(test.server_url, 'http://example.org')
        finally:
            del _MyTestCase.server_url

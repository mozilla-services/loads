import unittest
from loads.case import TestCase


class MyTestCase(TestCase):
    def test_one(self):
        pass


class TestTestCase(unittest.TestCase):

    def test_fake(self):
        case = MyTestCase('test_one')
        self.assertRaises(ValueError, case.app.get, 'boh')

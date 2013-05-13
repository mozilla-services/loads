import unittest
from loads.util import resolve_name


class TestUtil(unittest.TestCase):

    def test_resolve(self):

        ob = resolve_name('loads.tests.test_util.TestUtil')
        self.assertTrue(ob is TestUtil)

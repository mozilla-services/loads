import unittest

from loads.measure import Session
from loads import _patch  # NOQA

__version__ = '0.1'


class TestCase(unittest.TestCase):
    def __init__(self, test_name):
        unittest.TestCase.__init__(self, test_name)
        self.session = Session(self)

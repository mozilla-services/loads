import unittest
from loads import Session


class TestWebSite(unittest.TestCase):

    def setUp(self):
        self.session = Session(self)

    def test_something(self):
        res = self.session.get('http://faitmain.org/index.html')
        #self.assertTrue('Search' in res.content)


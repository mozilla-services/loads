import unittest
from loads import Session


class TestWebSite(unittest.TestCase):

    def setUp(self):
        self.session = Session()

    def test_something(self):
        res = self.session.get('http://localhost:9200')
        self.assertTrue('Search' in res.content)


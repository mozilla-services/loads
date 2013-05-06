import unittest
from loads import TestCase


class TestWebSite(TestCase):

    def test_something(self):
        res = self.session.get('http://faitmain.org/index.html')
        #self.assertTrue('Search' in res.content)


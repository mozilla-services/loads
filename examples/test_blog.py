import unittest
from loads import Session


class TestWebSite(unittest.TestCase):


    def setUp(self):
        self.session = Session()

    def test_something(self):


        res = self.session.get('http://blog.ziade.org')
        self.assertTrue('ziade' in res.content)


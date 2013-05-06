from loads import TestCase


class TestWebSite(TestCase):

    def test_something(self):
        res = self.session.get('http://localhost:9200')
        self.assertTrue('Search' in res.content)

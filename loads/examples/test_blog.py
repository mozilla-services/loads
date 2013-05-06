from loads import TestCase


class TestWebSite(TestCase):

    def test_something(self):
        res = self.session.get('http://localhost:9200')
        self.assertTrue('Search' in res.content)

    def _test_will_fail(self):
        res = self.session.get('http://localhost:9200')
        self.assertTrue('xFsj' in res.content)

    def _test_will_error(self):
        res = self.session.get('http://localhost:9200')
        raise ValueError(res)

from loads.stream.collector import StreamCollector, Hit, Test
from unittest import TestCase
import datetime

TIME1 = datetime.datetime(2013, 5, 14, 0, 51, 8)
TIME2 = datetime.datetime(2013, 5, 14, 0, 53, 8)


class TestStreamCollector(TestCase):

    def _get_data(self, url='http://notmyidea.org', method='GET',
                  status=200, started=None, elapsed=None, cycle=1, user=1,
                  current_cycle=1):
        started = started or TIME1
        loads_status = (cycle, user, current_cycle)
        return {'elapsed': elapsed or 2.0,
                'started': started,
                'status': status,
                'url': url,
                'method': method,
                'loads_status': loads_status}

    def test_push_hits(self):
        collector = StreamCollector()
        collector.push('hit', self._get_data())
        self.assertEquals(len(collector.hits), 1)

    def test_nb_hits(self):
        collector = StreamCollector()
        collector.push('hit', self._get_data())
        collector.push('hit', self._get_data())
        collector.push('hit', self._get_data())
        self.assertEquals(collector.nb_hits, 3)
        self.assertEquals(len(collector.hits), 3)

    def test_average_request_time_without_filter(self):
        collector = StreamCollector()
        collector.push('hit', self._get_data(elapsed=1))
        collector.push('hit', self._get_data(elapsed=3))
        collector.push('hit', self._get_data(elapsed=2))
        collector.push('hit', self._get_data(url='http://another-one',
                                                 elapsed=3))
        self.assertEquals(collector.average_request_time(), 2.25)

    def test_average_request_time_with_url_filtering(self):

        collector = StreamCollector()
        collector.push('hit', self._get_data(elapsed=1))
        collector.push('hit', self._get_data(elapsed=3))
        collector.push('hit', self._get_data(elapsed=2))
        collector.push('hit', self._get_data(url='http://another-one',
                                                 elapsed=3))
        # We want to filter out some URLs
        avg = collector.average_request_time('http://notmyidea.org')
        self.assertEquals(avg, 2.0)

        avg = collector.average_request_time('http://another-one')
        self.assertEquals(avg, 3.0)

    def test_average_request_time_with_cycle_filtering(self):
        collector = StreamCollector()
        collector.push('hit', self._get_data(elapsed=1, cycle=1))
        collector.push('hit', self._get_data(elapsed=3, cycle=2))
        collector.push('hit', self._get_data(elapsed=2, cycle=3))
        collector.push('hit', self._get_data(elapsed=3, cycle=3))

        avg = collector.average_request_time(cycle=3)
        self.assertEquals(avg, 2.5)

        # try adding another filter on the URL
        collector.push('hit', self._get_data(elapsed=3, cycle=3,
                                             url='http://another-one'))
        avg = collector.average_request_time(cycle=3,
                                                 url='http://notmyidea.org')
        self.assertEquals(avg, 2.5)

        self.assertEquals(collector.average_request_time(cycle=3),
                          2.6666666666666665)

    def test_average_request_time_when_no_data(self):
        collector = StreamCollector()
        self.assertEquals(collector.average_request_time(), None)

    def test_urls(self):
        collector = StreamCollector()
        collector.push('hit', self._get_data())
        collector.push('hit', self._get_data(url='http://another-one'))

        urls = set(['http://notmyidea.org', 'http://another-one'])
        self.assertEquals(collector.urls, urls)

    def test_hits_success_rate(self):
        collector = StreamCollector()
        collector.push('hit', self._get_data(status=200))
        collector.push('hit', self._get_data(status=200))
        collector.push('hit', self._get_data(status=200))
        collector.push('hit', self._get_data(status=200))
        collector.push('hit', self._get_data(status=400, cycle=2))

        self.assertEquals(collector.hits_success_rate(), 0.8)
        self.assertEquals(collector.hits_success_rate(cycle=1), 1)

    def test_requests_per_second(self):
        collector = StreamCollector()
        for x in range(20):
            collector.push('hit', self._get_data(status=200))

        collector.start_time = TIME1
        collector.stop_time = TIME2
        self.assertTrue(0.16 < collector.requests_per_second() < 0.17)

    def test_average_test_duration(self):
        t = Test(TIME1)
        t.end = TIME2

        collector = StreamCollector()
        collector.tests['toto', 1] = t
        collector.tests['tutu', 1] = t

        self.assertEquals(collector.average_test_duration(), 120)

    def test_tests_per_second(self):
        collector = StreamCollector()
        for x in range(20):
            collector.startTest('rainbow', x, 1, 1)

        collector.start_time = TIME1
        collector.stop_time = TIME2
        self.assertTrue(0.16 < collector.tests_per_second() < 0.17)


class TestHits(TestCase):

    def test_loads_status_default_to_None(self):
        elapsed = started = None
        h = Hit(url='http://notmyidea.org',
                method='GET',
                status=200,
                started=started,
                elapsed=elapsed,
                loads_status=None)
        self.assertEquals(h.cycle, None)
        self.assertEquals(h.user, None)
        self.assertEquals(h.current_cycle, None)

    def test_loads_status_extract_values(self):
        elapsed = started = None
        h = Hit(url='http://notmyidea.org',
                method='GET',
                status=200,
                started=started,
                elapsed=elapsed,
                loads_status=(1, 2, 3))

        self.assertEquals(h.cycle, 1)
        self.assertEquals(h.user, 2)
        self.assertEquals(h.current_cycle, 3)


class TestTest(TestCase):

    def test_duration_is_none_if_not_finished(self):
        test = Test()
        # no end value is provided
        self.assertEquals(test.duration, None)

    def test_duration_is_valid(self):
        test = Test(TIME1)
        test.end = TIME2
        self.assertEquals(test.duration, 120)

    def test_success_rate_when_none(self):
        test = Test()
        self.assertEquals(test.success_rate, None)

    def test_success_rate_when_failures_and_success(self):
        test = Test()
        test.success = 2
        test.failures.append(0)  # Acts as a failure.
        test.failures.append(0)
        self.assertEquals(test.success_rate, 0.5)

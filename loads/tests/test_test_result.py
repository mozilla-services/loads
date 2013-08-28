from unittest2 import TestCase
from datetime import datetime, timedelta

from mock import Mock

from loads.results.base import TestResult, Hit, Test


TIME1 = datetime(2013, 5, 14, 0, 51, 8)
TIME2 = datetime(2013, 5, 14, 0, 53, 8)
_1 = timedelta(seconds=1)
_2 = timedelta(seconds=2)
_3 = timedelta(seconds=3)


class TestTestResult(TestCase):

    def _get_data(self, url='http://notmyidea.org', method='GET',
                  status=200, started=None, elapsed=None, series=1, user=1,
                  current_hit=1, current_user=1):
        started = started or TIME1
        loads_status = series, user, current_hit, current_user

        return {'elapsed': elapsed or 0.2000,
                'started': started,
                'status': status,
                'url': url,
                'method': method,
                'loads_status': loads_status}

    def test_add_hits(self):
        test_result = TestResult()
        test_result.add_hit(**self._get_data())
        self.assertEquals(len(test_result.hits), 1)

    def test_nb_hits(self):
        test_result = TestResult()
        test_result.add_hit(**self._get_data())
        test_result.add_hit(**self._get_data())
        test_result.add_hit(**self._get_data())
        self.assertEquals(test_result.nb_hits, 3)
        self.assertEquals(len(test_result.hits), 3)

    def test_average_request_time_without_filter(self):
        test_result = TestResult()
        test_result.add_hit(**self._get_data(elapsed=_1))
        test_result.add_hit(**self._get_data(elapsed=_3))
        test_result.add_hit(**self._get_data(elapsed=_2))
        test_result.add_hit(**self._get_data(url='http://another-one',
                                             elapsed=_3))
        self.assertEquals(test_result.average_request_time(), 2.25)

    def test_average_request_time_with_url_filtering(self):

        test_result = TestResult()
        test_result.add_hit(**self._get_data(elapsed=_1))
        test_result.add_hit(**self._get_data(elapsed=_3))
        test_result.add_hit(**self._get_data(elapsed=_2))
        test_result.add_hit(**self._get_data(url='http://another-one',
                                             elapsed=_3))
        # We want to filter out some URLs
        avg = test_result.average_request_time('http://notmyidea.org')
        self.assertEquals(avg, 2.0)

        avg = test_result.average_request_time('http://another-one')
        self.assertEquals(avg, 3.0)

    def test_average_request_time_with_series_filtering(self):
        test_result = TestResult()
        test_result.add_hit(**self._get_data(elapsed=_1, series=1))
        test_result.add_hit(**self._get_data(elapsed=_3, series=2))
        test_result.add_hit(**self._get_data(elapsed=_2, series=3))
        test_result.add_hit(**self._get_data(elapsed=_3, series=3))

        avg = test_result.average_request_time(series=3)
        self.assertEquals(avg, 2.5)

        # try adding another filter on the URL
        test_result.add_hit(**self._get_data(elapsed=_3, series=3,
                                             url='http://another-one'))
        avg = test_result.average_request_time(series=3,
                                               url='http://notmyidea.org')
        self.assertEquals(avg, 2.5)

        self.assertEquals(test_result.average_request_time(series=3),
                          2.6666666666666665)

    def test_average_request_time_when_no_data(self):
        test_result = TestResult()
        self.assertEquals(test_result.average_request_time(), 0)

    def test_urls(self):
        test_result = TestResult()
        test_result.add_hit(**self._get_data())
        test_result.add_hit(**self._get_data(url='http://another-one'))

        urls = set(['http://notmyidea.org', 'http://another-one'])
        self.assertEquals(test_result.urls, urls)

    def test_hits_success_rate(self):
        test_result = TestResult()
        for x in range(4):
            test_result.add_hit(**self._get_data(status=200))
        test_result.add_hit(**self._get_data(status=400, series=2))

        self.assertEquals(test_result.hits_success_rate(), 0.8)
        self.assertEquals(test_result.hits_success_rate(series=1), 1)

    def test_requests_per_second(self):
        test_result = TestResult()
        for x in range(20):
            test_result.add_hit(**self._get_data(status=200))

        test_result.start_time = TIME1
        test_result.stop_time = TIME2
        self.assertTrue(0.16 < test_result.requests_per_second() < 0.17)

    def test_average_test_duration(self):
        t = Test(TIME1)
        t.end = TIME2

        test_result = TestResult()
        test_result.tests['toto', 1] = t
        test_result.tests['tutu', 1] = t

        self.assertEquals(test_result.average_test_duration(), 120)

    def test_tests_per_second(self):
        test_result = TestResult()
        for x in range(20):
            test_result.startTest('rainbow', (1, 1, x, 1))

        test_result.start_time = TIME1
        test_result.stop_time = TIME2
        self.assertTrue(0.16 < test_result.tests_per_second() < 0.17)

    def test_get_tests_filters_series(self):
        test_result = TestResult()

        test_result.tests['bacon', 1] = Test(name='bacon', series=1)
        test_result.tests['egg', 1] = Test(name='egg', series=1)
        test_result.tests['spam', 2] = Test(name='spam', series=2)

        self.assertEquals(len(test_result._get_tests(series=1)), 2)

    def test_get_tests_filters_names(self):
        test_result = TestResult()

        test_result.tests['bacon', 1] = Test(name='bacon', series=1)
        test_result.tests['bacon', 2] = Test(name='bacon', series=2)
        test_result.tests['spam', 2] = Test(name='spam', series=2)

        self.assertEquals(len(test_result._get_tests(name='bacon')), 2)

    def test_get_tests_filters_by_both_fields(self):
        test_result = TestResult()

        test_result.tests['bacon', 1] = Test(name='bacon', series=1)
        test_result.tests['bacon', 2] = Test(name='bacon', series=2)
        test_result.tests['spam', 2] = Test(name='spam', series=2)

        self.assertEquals(len(test_result._get_tests(name='bacon', series=2)),
                          1)

    def test_test_success_rate_when_not_started(self):
        # it should be none if no tests had been collected yet.
        test_result = TestResult()
        self.assertEquals(1, test_result.test_success_rate())

    def test_test_success_rate_is_correct(self):
        test_result = TestResult()

        loads_status = (1, 1, 1, 1)
        test_result.startTest('bacon', loads_status)
        test_result.addSuccess('bacon', loads_status)
        test_result.addFailure('bacon', 'A failure', loads_status)

        self.assertEquals(0.5, test_result.test_success_rate())

    def test_duration_is_zero_if_not_started(self):
        test_result = TestResult()
        self.assertEquals(test_result.duration, 0)

    def test_requests_per_second_if_not_started(self):
        test_result = TestResult()
        self.assertEquals(test_result.requests_per_second(), 0)

    def test_get_url_metrics(self):
        test_result = TestResult()
        test_result.average_request_time = Mock(return_value=0.5)
        test_result.hits_success_rate = Mock(return_value=0.9)
        test_result.add_hit(**self._get_data('http://notmyidea.org'))
        test_result.add_hit(**self._get_data('http://lolnet.org'))

        metrics = test_result.get_url_metrics()
        self.assertEquals(metrics['http://notmyidea.org'], {
            'average_request_time': 0.5,
            'hits_success_rate': 0.9})

        self.assertEquals(metrics['http://lolnet.org'], {
            'average_request_time': 0.5,
            'hits_success_rate': 0.9})

    def test_counters(self):
        test_result = TestResult()
        loads_status = (1, 1, 1, 1)
        test_result.incr_counter('bacon', loads_status, 'sent')
        test_result.incr_counter('bacon', loads_status, 'sent')
        test_result.incr_counter('bacon', loads_status, 'received')

        self.assertEqual(test_result.get_counter('sent'), 2)
        self.assertEqual(test_result.get_counter('received', test='bacon'), 1)
        self.assertEqual(test_result.get_counter('bacon', 'xxxx'), 0)
        self.assertEqual(test_result.get_counter('xxx', 'xxxx'), 0)

    def test_socket_count(self):
        test_result = TestResult()

        # Open 5 sockets
        for _ in range(5):
            test_result.socket_open()

        self.assertEquals(test_result.sockets, 5)
        self.assertEquals(test_result.opened_sockets, 5)
        self.assertEquals(test_result.closed_sockets, 0)

        for _ in range(4):
            test_result.socket_close()

        self.assertEquals(test_result.sockets, 1)
        self.assertEquals(test_result.opened_sockets, 5)
        self.assertEquals(test_result.closed_sockets, 4)


class TestHits(TestCase):

    def test_loads_status_default_to_None(self):
        started = None
        h = Hit(url='http://notmyidea.org',
                method='GET',
                status=200,
                started=started,
                elapsed=0.0,
                loads_status=None)
        self.assertEquals(h.series, None)
        self.assertEquals(h.user, None)
        self.assertEquals(h.current_hit, None)

    def test_loads_status_extract_values(self):
        started = None
        h = Hit(url='http://notmyidea.org',
                method='GET',
                status=200,
                started=started,
                elapsed=0.0,
                loads_status=(1, 2, 3, 4))

        self.assertEquals(h.series, 1)
        self.assertEquals(h.user, 2)
        self.assertEquals(h.current_hit, 3)


class TestTest(TestCase):

    def test_duration_is_zero_if_not_finished(self):
        test = Test()
        # no end value is provided
        self.assertEquals(test.duration, 0)

    def test_duration_is_valid(self):
        test = Test(TIME1)
        test.end = TIME2
        self.assertEquals(test.duration, 120)

    def test_success_rate_when_none(self):
        test = Test()
        self.assertEquals(test.success_rate, 1)

    def test_success_rate_when_failures_and_success(self):
        test = Test()
        test.success = 2
        test.failures.append(0)  # Acts as a failure.
        test.failures.append(0)
        self.assertEquals(test.success_rate, 0.5)

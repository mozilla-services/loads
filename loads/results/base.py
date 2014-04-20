import itertools
from collections import defaultdict

from datetime import datetime, timedelta
from loads.util import get_quantiles, total_seconds, seconds_to_time, unbatch


class TestResult(object):
    """Data TestResult.

    This is the class receiving all the information about the tests and the
    requests.

    Consumes the data passed to it and provide convenient APIs to read this
    data back. This can be useful if you want to transform this data to create
    reports, but it doesn't assume any representation for the output.
    """

    __test__ = False  # This is not something to run as a test.

    def __init__(self, config=None, args=None):
        self.config = config
        self.hits = []
        self.tests = {}
        self.opened_sockets = self.closed_sockets = 0
        self.socket_data_received = 0
        self.start_time = None
        self.stop_time = None
        self.observers = []
        self.args = args

    def __str__(self):
        duration = seconds_to_time(self.duration)
        msg = 'Ran %d tests in %s. %d hits, %.2f RPS.' % (
            self.nb_finished_tests,
            duration,
            self.nb_hits,
            self.requests_per_second())

        if self.socket > 0:
            msg += ' %s sockets opened, Bytes thru sockets %d' % (
                self.socket,
                self.socket_data_received)

        return msg

    def close(self):
        pass

    @property
    def project_name(self):
        return self.args.get('project_name', 'N/A')

    @property
    def nb_finished_tests(self):
        return len(self._get_tests(finished=True))

    @property
    def nb_hits(self):
        return len(self.hits)

    @property
    def duration(self):
        end = self.stop_time or datetime.utcnow()
        if self.start_time is None:
            return 0

        return total_seconds(end - self.start_time)

    @property
    def nb_failures(self):
        return sum([len(t.failures) for t in self._get_tests()])

    @property
    def nb_errors(self):
        return sum([len(t.errors) for t in self._get_tests()])

    @property
    def nb_success(self):
        return sum([t.success for t in self._get_tests()])

    @property
    def errors(self):
        return itertools.chain((t.errors for t in (self._get_tests())))

    @property
    def failures(self):
        return itertools.chain((t.failures for t in (self._get_tests())))

    @property
    def urls(self):
        """Returns the URLs that had been called."""
        return set([h.url for h in self.hits])

    @property
    def nb_tests(self):
        return len(self.tests)

    @property
    def sockets(self):
        return self.opened_sockets - self.closed_sockets

    def _get_hits(self, url=None, series=None):
        """Filters the hits with the given parameters.

        :param url:
            The url you want to filter with. Only the hits targetting this URL
            will be returned.

        :param series:
            Only the hits done during this series will be returned.
        """
        def _filter(_hit):
            if series is not None and _hit.series != series:
                return False

            if url is not None and _hit.url != url:
                return False

            return True

        return filter(_filter, self.hits)

    def _get_tests(self, name=None, series=None, finished=None, user=None):
        """Filters the tests with the given parameters.

        :param name:
            The name of the test you want to filter on.

        :param series:
            The series key you want to filter on.

        :param finished:
            Return only the finished or unfinished tests

        :param user:
            The user key to filter on.
        """
        def _filter(test):
            if name is not None and test.name != name:
                return False
            if series is not None and test.series != series:
                return False
            if finished is not None and test.finished != finished:
                return False
            return True

        return filter(_filter, self.tests.values())

    def average_request_time(self, url=None, series=None):
        """Computes the average time a request takes (in seconds)

        :param url:
            The url we want to know the average request time. Could be
            `None` if you want to get the overall average time of a request.
        :param series:
            You can filter by the series, to only know the average request time
            during a particular series.
        """
        elapsed = [total_seconds(h.elapsed)
                   for h in self._get_hits(url, series)]

        if elapsed:
            return float(sum(elapsed)) / len(elapsed)
        else:
            return 0

    def get_request_time_quantiles(self, url=None, series=None):
        elapsed = [total_seconds(h.elapsed)
                   for h in self._get_hits(url=url, series=series)]

        # XXX Cache these results, they might be long to compute.
        return get_quantiles(elapsed, (0, 0.1, 0.5, 0.9, 1))

    def hits_success_rate(self, url=None, series=None):
        """Returns the success rate for the filtered hits.

        (A success is a hit with a status code of 2XX or 3XX).

        :param url: the url to filter on.
        :param hit: the hit to filter on.
        """
        hits = list(self._get_hits(url, series))
        success = [h for h in hits if 200 <= h.status < 400]

        if hits:
            return float(len(success)) / len(hits)
        else:
            return 0

    def get_url_metrics(self):
        urls = defaultdict(dict)
        for url in self.urls:
            for metric in ('average_request_time', 'hits_success_rate'):
                urls[url][metric] = getattr(self, metric)(url)
        return urls

    def tests_per_second(self):
        delta = self.stop_time - self.start_time
        return self.nb_tests / total_seconds(delta)

    def average_test_duration(self, test=None, series=None):
        durations = [t.duration for t in self._get_tests(test, series)
                     if t is not None]
        if durations:
            return float(sum(durations)) / len(durations)

    def test_success_rate(self, test=None, series=None):
        rates = [t.success_rate for t in self._get_tests(test, series)]
        if rates:
            return sum(rates) / len(rates)
        return 1

    def requests_per_second(self, url=None, hit=None):
        if self.duration == 0:
            return 0
        return float(len(self.hits)) / self.duration

    # batched results
    def batch(self, **args):
        for field, message in unbatch(args):
            if hasattr(self, field):
                    getattr(self, field)(**message)

    # These are to comply with the APIs of unittest.
    def startTestRun(self, agent_id=None, when=None):
        if when is None:
            when = datetime.utcnow()

        if agent_id is None:
            self.start_time = when

    def stopTestRun(self, agent_id=None):
        # we don't want to start multiple time the test run
        if agent_id is None:
            self.stop_time = datetime.utcnow()

    def startTest(self, test, loads_status, agent_id=None):
        hit, user, current_hit, current_user = loads_status
        key = self._get_key(test, loads_status, agent_id)
        if key not in self.tests:
            self.tests[key] = Test(name=test, hit=hit, user=user)

    def stopTest(self, test, loads_status, agent_id=None):
        hit, user, current_hit, current_user = loads_status
        t = self._get_test(test, loads_status, agent_id)
        t.end = datetime.utcnow()

    def addError(self, test, exc_info, loads_status, agent_id=None):
        test = self._get_test(test, loads_status, agent_id)
        test.errors.append(exc_info)

    def addFailure(self, test, exc_info, loads_status, agent_id=None):
        test = self._get_test(test, loads_status, agent_id)
        test.failures.append(exc_info)

    def addSuccess(self, test, loads_status, agent_id=None):
        test = self._get_test(test, loads_status, agent_id)
        test.success += 1

    def incr_counter(self, test, loads_status, name, agent_id=None):
        test = self._get_test(test, loads_status, agent_id)
        test.incr_counter(name)

    def get_counter(self, name, test=None):
        return sum([t.get_counter(name) for t in self._get_tests(name=test)])

    def get_counters(self, test=None):
        counters = defaultdict(int)
        for test in self._get_tests(name=test):
            for name, value in test.get_counters().items():
                counters[name] += value
        return counters

    def add_hit(self, **data):
        self.hits.append(Hit(**data))

    def socket_open(self, agent_id=None):
        self.opened_sockets += 1

    def socket_close(self, agent_id=None):
        self.closed_sockets += 1

    def socket_message(self, size, agent_id=None):
        self.socket_data_received += size

    def __getattribute__(self, name):
        # call the observer's "push" method after calling the method of the
        # test_result itself.
        attr = object.__getattribute__(self, name)
        if name in ('startTestRun', 'stopTestRun', 'startTest', 'stopTest',
                    'addError', 'addFailure', 'addSuccess', 'add_hit',
                    'socket_open', 'socket_message', 'incr_counter'):

            def wrapper(*args, **kwargs):
                ret = attr(*args, **kwargs)
                for obs in self.observers:
                    obs.push(name, *args, **kwargs)
                return ret
            return wrapper
        return attr

    def add_observer(self, observer):
        self.observers.append(observer)

    def _get_key(self, test, loads_status, agent_id):
        return tuple((str(test),) + tuple(loads_status) + (agent_id,))

    def _get_test(self, test, loads_status, agent_id):
        key = self._get_key(test, loads_status, agent_id)
        if key not in self.tests:
            self.startTest(test, loads_status, agent_id)

        return self.tests[key]

    def sync(self, run_id):
        pass


class Hit(object):
    """Represent a hit.

    Used for later computation.
    """
    def __init__(self, url, method, status, started, elapsed, loads_status,
                 agent_id=None):
        self.url = url
        self.method = method
        self.status = status
        self.started = started
        if not isinstance(elapsed, timedelta):
            elapsed = timedelta(seconds=elapsed)

        self.elapsed = elapsed

        loads_status = loads_status or (None, None, None, None)
        (self.series, self.user, self.current_hit,
         self.current_user) = loads_status

        self.agent_id = agent_id


class Test(object):
    """Represent a test that had been run."""

    def __init__(self, start=None, **kwargs):
        self.start = start or datetime.utcnow()
        self.end = None
        self.name = None
        self.hit = None
        self.user = None

        self.failures = []
        self.errors = []
        self.success = 0
        self._counters = defaultdict(int)

        for key, value in kwargs.items():
            setattr(self, key, value)

    def incr_counter(self, name):
        self._counters[name] += 1

    @property
    def finished(self):
        return bool(self.end)

    @property
    def duration(self):
        if self.end is not None:
            return total_seconds(self.end - self.start)
        else:
            return 0

    @property
    def success_rate(self):
        total = self.success + len(self.failures) + len(self.errors)
        if total != 0:
            return float(self.success) / total
        return 1  # Every of the 0 runs we had was successful

    def __repr__(self):
        return ('<Test %s. errors: %s, failures: %s, success: %s>'
                % (self.name, len(self.errors), len(self.failures),
                   self.success))

    def get_error(self):
        """Returns the first encountered error"""
        if not self.errors:
            return

        return self.errors[0]

    def get_failure(self):
        """Returns the first encountered failure"""
        if not self.failures:
            return

        return self.failures[0]

    def get_counter(self, name):
        return self._counters[name]

    def get_counters(self):
        return self._counters

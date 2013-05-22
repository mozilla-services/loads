from datetime import datetime
from collections import defaultdict


class TestResult(object):
    """Data TestResult.

    This is the class receiving all the information about the tests and the
    requests.

    Consumes the data passed to it via :method push: and provide convenient
    APIs to read this data back. This can be useful if you want to transform
    this data to create reports, but it doesn't assume any representation for
    the output.
    """

    def __init__(self, config=None):
        self.config = config
        self.hits = []
        self.tests = defaultdict(Test)
        self.sockets = 0
        self.socket_data_received = 0
        self.start_time = None
        self.stop_time = None
        self.observers = []

    @property
    def nb_hits(self):
        return len(self.hits)

    @property
    def duration(self):
        end = self.stop_time or datetime.utcnow()
        return (end - self.start_time).seconds

    @property
    def has_errors_or_failures(self):
        tests = self._get_tests()
        errors = 0
        for fail in ('errors', 'failures'):
            errors += sum([len(getattr(t, fail)) for t in tests])
        return errors

    @property
    def urls(self):
        """Returns the URLs that had been called."""
        return set([h.url for h in self.hits])

    @property
    def nb_tests(self):
        return len(self.tests)

    def _get_hits(self, url=None, cycle=None):
        """Filters the hits with the given parameters.

        :param url:
            The url you want to filter with. Only the hits targetting this URL
            will be returned.

        :param cycle:
            Only the hits done during this cycle will be returned.
        """

        def _filter(hit):
            if cycle is not None and hit.cycle != cycle:
                return False

            if url is not None and hit.url != url:
                return False

            return True

        return filter(_filter, self.hits)

    def _get_tests(self, name=None, cycle=None):
        """Filters the tests with the given parameters.

        :param name:
            The name of the test you want to filter on.

        :param cycle:
            The cycle you want to filter on.
        """
        def _filter(test):
            if name is not None and test.name != name:
                return False
            if cycle is not None and test.cycle != cycle:
                return False
            return True

        return filter(_filter, self.tests.values())

    def average_request_time(self, url=None, cycle=None):
        """Computes the average time a request takes.

        :param url:
            The url we want to know the average request time. Could be
            `None` if you want to get the overall average time of a request.
        :param cycle:
            You can filter by the cycle, to only know the average request time
            during a particular cycle.
        """
        elapsed = [h.elapsed for h in self._get_hits(url, cycle)]

        if elapsed:
            return float(sum(elapsed)) / len(elapsed)

    def hits_success_rate(self, url=None, cycle=None):
        """Returns the success rate for the filtered hits.

        (A success is a hit with a status code of 2XX or 3XX).

        :param url: the url to filter on.
        :param cycle: the cycle to filter on.
        """
        hits = list(self._get_hits(url, cycle))
        success = [h for h in hits if 200 <= h.status < 400]

        return float(len(success)) / len(hits)

    def tests_per_second(self):
        return (self.nb_tests /
                float((self.stop_time - self.start_time).seconds))

    def average_test_duration(self, test=None, cycle=None):
        durations = [t.duration for t in self._get_tests(test, cycle)
                     if t is not None]
        if durations:
            return float(sum(durations)) / len(durations)

    def test_success_rate(self, test=None, cycle=None):
        rates = [t.success_rate for t in self._get_tests(test, cycle)]
        if rates:
            return sum(rates) / len(rates)

    def requests_per_second(self, url=None, cycle=None):
        return float(len(self.hits)) / self.duration

    # These are to comply with the APIs of unittest.
    def startTestRun(self):
        self.start_time = datetime.utcnow()

    def stopTestRun(self):
        self.stop_time = datetime.utcnow()

    def startTest(self, test, cycle, user, current_cycle):
        ob = self.tests[test, cycle]
        ob.name = test
        ob.cycle = cycle
        ob.user = user

    def stopTest(self, test, cycle, user, current_cycle):
        self.tests[test, cycle].end = datetime.utcnow()

    def addError(self, test, exc_info, cycle, user, current_cycle):
        self.tests[test, cycle].errors.append(exc_info)

    def addFailure(self, test, exc_info, cycle, user, current_cycle):
        self.tests[test, cycle].failures.append(exc_info)

    def addSuccess(self, test, cycle, user, current_cycle):
        self.tests[test, cycle].success += 1

    def add_hit(self, **data):
        self.hits.append(Hit(**data))

    def socket_open(self):
        self.sockets += 1

    def socket_message(self, size):
        self.socket_data_received += size

    def __getattribute__(self, name):
        # That's to manage the observers. Each time one of the methods used to
        # add data in the test_result is called, the obeserver's same method will
        # be called as well, so it can update its state if it wants.

        attr = object.__getattribute__(self, name)
        if name in ('startTestRun', 'stopTestRun', 'startTest', 'stopTest',
                    'addError', 'addFailure', 'addSuccess', 'add_hit',
                    'socket_open', 'socket_message'):

            def wrapper(*args, **kwargs):
                ret = attr(*args, **kwargs)
                for obs in self.observers:
                    obs.push(name, *args, **kwargs)
                return ret
            return wrapper
        return attr

    def add_observer(self, observer):
        self.observers.append(observer)


class Hit(object):
    """Represent a hit.

    Used for later computation.
    """
    def __init__(self, url, method, status, started, elapsed, loads_status):
        self.url = url
        self.method = method
        self.status = status
        self.started = started
        self.elapsed = elapsed
        if loads_status is not None:
            self.cycle, self.user, self.current_cycle = loads_status
        else:
            self.cycle, self.user, self.current_cycle = None, None, None


class Test(object):
    """Represent a test that had been run."""

    def __init__(self, start=None, **kwargs):
        self.start = start or datetime.utcnow()
        self.end = None
        self.name = None
        self.cycle = None
        self.failures = []
        self.errors = []
        self.success = 0
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def duration(self):
        if self.end is not None:
            return (self.end - self.start).seconds
        else:
            return None

    @property
    def success_rate(self):
        total = self.success + len(self.failures) + len(self.errors)
        if total != 0:
            return float(self.success) / total

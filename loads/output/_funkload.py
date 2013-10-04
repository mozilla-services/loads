from calendar import timegm
from datetime import datetime
from itertools import chain
import platform
import os.path
from traceback import format_tb
from xml.sax.saxutils import quoteattr

from loads import __version__
from loads.util import total_seconds
from loads.results.base import Test


# This may be compatible with earlier versions of funkload, but that's the
# one that had been used when writing this output class.
FUNKLOAD_VERSION = "1.17.0"
LOADS_EXPORT_VERSION = "{0}-0.2".format(__version__)


# XML templates
_HEADER = '<funkload version="{version}" time="{time}">'
_FOOTER = '</funkload>'
_CONFIG = '<config key="{key}" value="{value}"/>'
_RESPONSE = '''\
<response
    cycle="{cycle:03}" cvus="{cvus:03}" thread="{thread:03}" suite="" name=""
    step="001" number="001" type="{method}" result="Successful" url="{url}"
    code="{status}" description="" time="{started}" duration="{elapsed}" />'''
_RESULT = '''\
<testResult
    cycle="{cycle:03}" cvus="{cvus:03}" thread="{thread:03}" suite="{suite}"
    name="{name}" time="{time}" result="{result}" steps="1"
    duration="{duration}" connection_duration="0" requests="{requests}"
    pages="{requests}" xmlrpc="0" redirects="0" images="0" links="0"
    {traceback}/>'''


class FunkloadOutput(object):
    """Generates outputs in the (undocumented) Funkload XML format.

    These reports can then be used with the the `fl-build-report <filename>`
    command-line tool to generate reports about the load.

    """
    name = 'funkload'
    options = {'filename': ('Full path where to output funkload XML files',
                            str, 'funkload-report.xml', True)}

    def __init__(self, test_results, args):
        self.filename = args['output_funkload_filename']
        self.args = args

        self._test_results = test_results
        self.tests = {}
        self.current_tests = {}
        self.nodes = []
        self.test_url = args.get('server_url', '')
        self.entries = []

    def _get_key(self, test, loads_status, agent_id):
        return tuple((str(test),) + tuple(loads_status) + (agent_id,))

    def _get_test(self, test, loads_status, agent_id):
        key = self._get_key(test, loads_status, agent_id)
        if key not in self.tests:
            self.startTest(test, loads_status, agent_id)

        return self.tests[key]

    def _get_current_test(self, loads_status, agent_id):
        # The current 'active' test for this status and agent
        key = self._get_key(None, loads_status, agent_id)
        return self.current_tests.get(key)

    #
    # Observer API
    #

    def push(self, called_method, *args, **kwargs):
        # Delegate to per-called-method handlers
        m = getattr(self, called_method, None)
        if m is not None:
            m(*args, **kwargs)

    def flush(self, _FOOTER=_FOOTER):
        self.nodes.append(_FOOTER)
        with open(self.filename, 'w') as f:
            for node in self.nodes:
                f.write(node + '\n')

    #
    # Push handlers
    #

    def startTestRun(self, agent_id=None, when=None, _HEADER=_HEADER,
                     _CONFIG=_CONFIG):
        self.start_time = when or datetime.utcnow()
        cycles = self.args['users'] or ['1']
        if isinstance(cycles, str):
            cycles = cycles.split(':')
        self.cycle_ids = dict((c, i) for i, c in enumerate(cycles))
        module, class_, method = self.args['fqn'].rsplit('.', 2)
        config = {
            'id': method,
            'class': class_,
            'class_description': 'Loads Funkload export {0}'.format(
                LOADS_EXPORT_VERSION),
            'cycle_time': '0',  # until issue #99 is resolved
            'cycles': cycles,
            'description': 'No test description',
            'duration': self.args['duration'] or '1',
            'log_xml': os.path.abspath(self.filename),
            'method': method,
            'module': module,
            'node': platform.node(),
            'python_version': platform.python_version(),
            'server_url': self.test_url,

            # Maybe we can drop the following ones; depending if
            # funkload complains when they're not present
            # (but they don't really mean anything to loads.)
            'class_title': '',
            'configuration_file': '',
            'sleep_time': '0.0',
            'sleep_time_max': '0.0',
            'sleep_time_min': '0.0',
            'startup_delay': '0.0',
        }

        self.nodes.append(_HEADER.format(
            version=FUNKLOAD_VERSION, time=self.start_time.isoformat()))

        for key, value in config.items():
            if value is not None:
                self.nodes.append(_CONFIG.format(key=key, value=value))

    def add_hit(self, loads_status=None, started=0, elapsed=0, url='',
                method="GET", status=200, agent_id=None, _RESPONSE=_RESPONSE):
        """Generates a funkload XML item with the data coming from the request.

        Adds the new XML node to the list of nodes for this output.

        """
        hit, user, current_hit, current_user = loads_status

        self.nodes.append(_RESPONSE.format(
            cycle=self.cycle_ids[user],
            cvus=user,
            method=method.lower(),
            url=url,
            status=status,
            thread=current_user,
            started=timegm(started.timetuple()),
            elapsed=total_seconds(elapsed)))

        test = self._get_current_test(loads_status, agent_id)
        if test:
            test.incr_counter('__funkload_requests')

    def addSuccess(self, test, loads_status, agent_id=None):
        test = self._get_test(test, loads_status, agent_id)
        test.success += 1

    def addError(self, test, exc_info, loads_status, agent_id=None):
        test = self._get_test(test, loads_status, agent_id)
        test.errors.append(exc_info[2])

    def addFailure(self, test, exc_info, loads_status, agent_id=None):
        test = self._get_test(test, loads_status, agent_id)
        test.failures.append(exc_info[2])

    def startTest(self, test, loads_status=None, agent_id=None):
        hit, user = loads_status[:2]
        key = self._get_key(test, loads_status, agent_id)
        current = self._get_key(None, loads_status, agent_id)
        t = Test(name=test, hit=hit, user=user)
        # also record the *current* test for the given loads_status
        self.current_tests[current] = self.tests[key] = t

    def stopTest(self, test, loads_status=None, agent_id=None,
                 _RESULT=_RESULT):
        """Generates funkload XML items with the data concerning test results.

        Adds new XML nodes to the list of nodes for this output.

        """
        hit, user, current_hit, current_user = loads_status
        t = self._get_test(test, loads_status, agent_id)
        t.end = datetime.utcnow()
        try:
            requests = t.get_counter('__funkload_requests')
        except KeyError:
            requests = 0

        per_test = {
            'cycle': self.cycle_ids[user],
            'cvus': user,
            'duration': t.duration,
            'name': test._testMethodName,
            'suite': test.__class__.__name__,
            'thread': current_user,
            'time': timegm(t.start.timetuple()),
            'requests': requests,
        }

        for traceback in chain(t.errors, t.failures):
            traceback = 'traceback={0}'.format(
                quoteattr('\n'.join(format_tb(traceback))))
            self.nodes.append(_RESULT.format(
                result='Failure',
                traceback=traceback,
                **per_test))

        for _ in xrange(t.success):
            self.nodes.append(_RESULT.format(
                result='Successful',
                traceback='',
                **per_test))

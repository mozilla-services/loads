import itertools
import platform
import uuid
from traceback import print_tb
from StringIO import StringIO

from datetime import datetime
from time import mktime

from loads.util import total_seconds

# This may be compatible with earlier versions of funkload, but that's the
# one that had been used when writing this output class.
FUNKLOAD_VERSION = "1.17.0"


class FunkloadOutput(object):
    """Generates outputs in the (non-documented) Funkload XML format.

    These reports can then be used with the the `fl-build-report <filename>`
    command-line tool to generate reports about the load.
    """
    name = 'funkload'
    options = {'filename': ('Full path where to output funkload XML files',
                            str, 'funkload-report.xml', True)}

    def __init__(self, test_results, args):
        self.filename = args['output_funkload_filename']
        self.args = args

        # Funkload want eacyh test to have a different ID.
        # XXX Maybe can we use the run id here?
        self.test_id = uuid.uuid4()
        self._test_results = test_results
        self.nodes = []
        self.test_url = ""

    def add_hit(self, cvus, method, url, status, started, elapsed):
        """Generates a funkload XML item with the data coming from the request.

        Adds the new XML node to the list of nodes for this output and return
        it.
        """
        node = ('<response cycle="000" cvus="{cvus}" thread="000" '
                'suite="" name="" '
                'step="001" number="001" type="{method}" result="Successful" '
                'url="{url}" code="{status}" description="" '
                'time="{started}" duration="{elapsed}" />').format(
            cvus=cvus,
            method=method,
            url=url,
            status=status,
            started=mktime(started.timetuple()),
            elapsed=total_seconds(elapsed))
        self.nodes.append(node)
        return node

    def add_test_result(self, status, cvus, time, duration, traceback=None):
        """Generates a funkload XML item with the data concerning a test
        result.

        Adds the new XML node to the list of nodes for this output and return
        it.
        """

        node = ('<testResult cycle="000" cvus="{cvus}" thread="000" '
                'suite="" name="" '
                'time="{time}" result="{result}" steps="1" '
                'duration="{duration}" '
                'connection_duration="" requests="" '
                'pages="" xmlrpc="" redirects="" images="" '
                'links=""').format(
            cvus=cvus,
            traceback=traceback,
            time=mktime(time.timetuple()),
            duration=duration,
            result=status.capitalize())
        if traceback:
            klass, error, tb = traceback
            container = StringIO()
            print_tb(tb, file=container)
            container.seek(0)
            tb = container.read()
            tb = tb.replace('"', '\'')
            node += ' traceback="{0}"'.format(tb)
        node += ' />'
        self.nodes.append(node)
        return node

    def push(self, *args, **kwargs):
        pass  # We aren't building the reports in real time.

    def flush(self):
        # At this stage, we normally have all the information we already
        # want, since the output class had been pingued each time we had a
        # new hit / success / error.
        #
        # The only thing we need to do is then to write the content to the
        # given file.
        config = {'id': self.test_id,
                  'class': self.args['fqn'],
                  'cycles': self.args['hits'],
                  'duration': self._test_results.duration,
                  'server_url': self.test_url,
                  'python_version': platform.python_version(),

                  # Maybe we can drop the following ones; depending if
                  # funkload complains when they're not present
                  # (but they don't really mean anything to loads.)
                  'description': '',
                  'class_title': '',
                  'class_description': '',
                  'module': '',
                  'method': '',
                  'sleep_time': '',
                  'startup_delay': '',
                  'sleep_time_min': '',
                  'sleep_time_max': '',
                  'cycle_time': '',
                  'configuration_file': '',
                  'log_xml': ''}

        self.nodes.append('<funkload version="{version}" time="{time}">'
            .format(version=FUNKLOAD_VERSION, time=datetime.now().isoformat()))

        for key, value in config.items():
            if value is not None:
                self.nodes.append('<config key="{key}" value="{value}"/>'
                    .format(key=key, value=value))

        for hit in self._test_results.hits:
            self.add_hit(cvus=hit.user * hit.series,
                         method=hit.method,
                         url=hit.url,
                         status=hit.status,
                         started=hit.started,
                         elapsed=hit.elapsed)
        for test in self._test_results.tests.values():
            for failure in itertools.chain(test.failures, test.errors):
                self.add_test_result(status='Failure',
                                     cvus=test.hit * test.user,
                                     time=test.start,
                                     duration=test.duration,
                                     traceback=failure)
            for x in range(test.success):
                self.add_test_result(status='Success',
                                     cvus=test.hit * test.user,
                                     time=test.start,
                                     duration=test.duration)

        self.nodes.append('</funkload>')
        with open(self.filename, 'w') as f:
            for node in self.nodes:
                f.write(node + '\n')

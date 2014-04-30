import unittest2
import os
from StringIO import StringIO
import sys
import contextlib
import re

import mock
from unittest2 import skipIf

from loads.main import main, add_options
from loads.tests.test_functional import start_servers, stop_servers
from loads.tests.support import hush
from loads import __version__


config = os.path.join(os.path.dirname(__file__), 'config.ini')


_WANTED = """\
Broker running on pid [0-9]+
10 agents registered
  - [0-9]+ on .*
  - [0-9]+ on .*
  - [0-9]+ on .*
  - [0-9]+ on .*
  - [0-9]+ on .*
  - [0-9]+ on .*
  - [0-9]+ on .*
  - [0-9]+ on .*
  - [0-9]+ on .*
  - [0-9]+ on .*
endpoints:
  - backend: ipc:///tmp/loads-back.ipc
  - frontend: ipc:///tmp/loads-front.ipc
  - heartbeat: tcp://0.0.0.0:9876
  - publisher: ipc:///tmp/loads-publisher.ipc
  - receiver: ipc:///tmp/loads-broker-receiver.ipc
  - register: ipc:///tmp/loads-reg.ipc
We have 1 run\(s\) right now:
  - .* with 10 agent\(s\)"""


@skipIf('TRAVIS' in os.environ, 'not running this on Travis')
class TestRunner(unittest2.TestCase):

    @classmethod
    def setUpClass(cls):
        if 'TRAVIS' in os.environ:
            return
        start_servers()

    @classmethod
    def tearDownClass(cls):
        if 'TRAVIS' in os.environ:
            return
        stop_servers()

    @hush
    def test_config(self):
        args = ['--config', config,
                'loads.examples.test_blog.TestWebSite.test_something',
                '--quiet']

        main(args)

    @contextlib.contextmanager
    def capture_stdout(self):
        output = StringIO()
        old = sys.stdout
        sys.stdout = output
        try:
            yield output
        except SystemExit:
            pass
        finally:
            sys.stdout = old
            output.seek(0)

    @hush
    def test_check_cluster(self):
        args = ['--check-cluster']

        with self.capture_stdout() as output:
            main(args)

        output = output.read().strip()
        self.assertTrue('Success: 10' in output, output)

    def test_help(self):
        args = []

        with self.capture_stdout() as output:
            main(args)

        self.assertTrue(output.read().strip().startswith('usage'))

    def test_version(self):
        args = ['--version']

        with self.capture_stdout() as output:
            main(args)

        self.assertEqual(output.read().strip(), __version__)

    def test_purge_broker(self):
        args = ['--purge-broker']

        with self.capture_stdout() as output:
            main(args)

        wanted = ['Nothing to purge.',
                  'We have 1 run(s) right now:\nPurged.']

        self.assertTrue(output.read().strip() in wanted)

    def test_ping_broker(self):
        args = ['--ping-broker']

        with self.capture_stdout() as output:
            main(args)

        output = output.read().strip()
        self.assertTrue(re.search(_WANTED, output) is not None, output)

    def test_add_options(self):

        class ClassA(object):
            name = 'classa'
            options = {'foo': ('helptext', int, 2, True)}

        class ClassB(object):
            name = 'classb'
            options = {'bar': ('helptext', str, 'bar', True)}

        parser = mock.MagicMock()
        items = [ClassA, ClassB]
        add_options(items, parser, fmt='--test-{name}-{option}')

        self.assertEquals(parser.add_argument.mock_calls[0],
                          mock.call('--test-classa-foo', default=2,
                                    type=int, help='helptext'))

        self.assertEquals(parser.add_argument.mock_calls[1],
                          mock.call('--test-classb-bar', default='bar',
                                    type=str, help='helptext'))

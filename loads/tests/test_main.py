import unittest2
import os
from StringIO import StringIO
import sys
import contextlib

import mock

from loads.main import main, add_options
from loads.tests.test_functional import start_servers
from loads.tests.support import hush
from loads import __version__


config = os.path.join(os.path.dirname(__file__), 'config.ini')


class TestRunner(unittest2.TestCase):

    @classmethod
    def setUpClass(cls):
        start_servers()

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

        self.assertTrue('Success: 3' in output.read().strip())

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

        res = [line.strip() for line in output.read().strip().split('\n')
               if line.strip() != '']

        wanted = ['Broker running on pid ',
                  '3 agents registered',
                  'endpoints:',
                  '- backend: ipc:///tmp/loads-back.ipc',
                  '- publisher: ipc:///tmp/loads-publisher.ipc',
                  '- register: ipc:///tmp/loads-reg.ipc',
                  '- frontend: ipc:///tmp/loads-front.ipc',
                  '- receiver: ipc:///tmp/loads-broker-receiver.ipc']

        for index, line in enumerate(wanted):
            self.assertTrue(res[index].startswith(line))

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

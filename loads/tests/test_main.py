import unittest2
import os

import mock

from loads.main import main, add_options
from loads.tests.test_functional import start_servers
from loads.tests.support import hush


config = os.path.join(os.path.dirname(__file__), 'config.ini')


class TestRunner(unittest2.TestCase):

    def setUp(self):
        start_servers()

    @hush
    def test_config(self):
        args = ['--config', config,
                'loads.examples.test_blog.TestWebSite.test_something',
                '--quiet']

        main(args)

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

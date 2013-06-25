import unittest
import os

from loads.main import main
from loads.tests.test_functional import start_servers
from loads.tests.support import hush


config = os.path.join(os.path.dirname(__file__), 'config.ini')


class TestRunner(unittest.TestCase):

    def setUp(self):
        start_servers()

    @hush
    def test_config(self):
        args = ['--config', config,
                'loads.examples.test_blog.TestWebSite.test_something',
                '--quiet']

        main(args)

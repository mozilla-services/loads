import pkg_resources

from loads import _patch  # NOQA
from loads.case import TestCase  # NOQA


__version__ = pkg_resources.get_distribution('loads').version

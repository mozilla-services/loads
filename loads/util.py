from contextlib import contextmanager
import datetime
import errno
import json
import logging
import logging.handlers
import math
import os
import sys
import tempfile
import urlparse

from gevent.socket import gethostbyname


logger = logging.getLogger('loads')


def set_logger(debug=False, name='loads', logfile='stdout'):
    # setting up the logger
    logger_ = logging.getLogger(name)
    logger_.setLevel(logging.DEBUG)

    if logfile == 'stdout':
        ch = logging.StreamHandler()
    else:
        ch = logging.handlers.RotatingFileHandler(logfile, mode='a+')

    if debug:
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)

    formatter = logging.Formatter('[%(asctime)s][%(name)s] %(message)s')
    ch.setFormatter(formatter)
    logger_.addHandler(ch)


class DateTimeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.timedelta):
            return obj.total_seconds()
        else:
            return super(DateTimeJSONEncoder, self).default(obj)


_CACHE = {}


def dns_resolve(url):
    if url in _CACHE:
        return _CACHE[url]

    parts = urlparse.urlparse(url)
    netloc = parts.netloc.rsplit(':')
    if len(netloc) == 1:
        netloc.append('80')
    original = netloc[0]
    resolved = gethostbyname(original)
    netloc = resolved + ':' + netloc[1]
    parts = (parts.scheme, netloc) + parts[2:]
    _CACHE[url] = urlparse.urlunparse(parts), original, resolved
    return _CACHE[url]


# taken from distutils2
def resolve_name(name):
    """Resolve a name like ``module.object`` to an object and return it.

    This functions supports packages and attributes without depth limitation:
    ``package.package.module.class.class.function.attr`` is valid input.
    However, looking up builtins is not directly supported: use
    ``__builtin__.name``.

    Raises ImportError if importing the module fails or if one requested
    attribute is not found.
    """
    if '.' not in name:
        # shortcut
        __import__(name)
        return sys.modules[name]

    # FIXME clean up this code!
    parts = name.split('.')
    cursor = len(parts)
    module_name = parts[:cursor]
    ret = ''

    while cursor > 0:
        try:
            ret = __import__('.'.join(module_name))
            break
        except ImportError:
            cursor -= 1
            module_name = parts[:cursor]

    if ret == '':
        raise ImportError(parts[0])

    for part in parts[1:]:
        try:
            ret = getattr(ret, part)
        except AttributeError, exc:
            raise ImportError(exc)

    return ret


@contextmanager
def temporary_file(suffix=''):
    """Creates a temporary file ready to be written into.

    This is a context manager, so that you can ask for a new file to write to
    inside the with block and don't care about closing the file nor deleting
    it.

    :param suffix: the suffix to eventually pass to the mkstemp operation.
    """
    fd, filename = tempfile.mkstemp(suffix)
    f = os.fdopen(fd, 'w+')
    yield (f, filename)
    f.close()


def get_percentiles(data, percentiles):
    """Computes the percentiles for the data array you pass along.

    This assumes that the data array you're passing is already sorted.

    :param data: the input array
    :param percentiles: a list of percentiles you want to compute, from 0.0 to
                        1.0

    Source: http://code.activestate.com/recipes/511478-finding-the-percentile-of-the-values/  # NOQA
    """
    def _percentile(N, percent):
        """
        Find the percentile of a list of values.

        @parameter N - is a list of values. Note N MUST BE already sorted.
        @parameter percent - a float value from 0.0 to 1.0.

        @return - the percentile of the values
        """
        if not N:
            return None

        k = (len(N) - 1) * percent
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return N[int(k)]
        d0 = N[int(f)] * (c - k)
        d1 = N[int(c)] * (k - f)
        return d0 + d1

    data = sorted(data)
    return tuple([_percentile(data, p) for p in percentiles])


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST or not os.path.isdir(path):
            raise

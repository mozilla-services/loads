from contextlib import contextmanager
import datetime
import json
import logging
import logging.handlers
import os
import sys
import tempfile
import urlparse
import math

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


def get_quantiles(data, quantiles):
    """Computes the quantiles for the data array you pass along.

    This assumes that the data array you're passing is already sorted.

    :param data: the input array
    :param quantiles: a list of quantiles you want to compute.

    This is an adapted version of an implementation by Ernesto P.Adorio Ph.D.
    UP Extension Program in Pampanga, Clark Field.

    Warning: this implentation is probably slow. We are using this atm to avoid
    depending on scipy, who have a much better and faster version, see
    scipy.stats.mstats.mquantiles

    References:
       http://reference.wolfram.com/mathematica/ref/Quantile.html
       http://wiki.r-project.org/rwiki/doku.php?id=rdoc:stats:quantile
       http://adorio-research.org/wordpress/?p=125

    """
    def _get_quantile(q, data_len):
        a, b, c, d = (1.0 / 3, 1.0 / 3, 0, 1)
        g, j = math.modf(a + (data_len + b) * q - 1)
        if j < 0:
                return data[0]
        elif j >= data_len:
                return data[data_len - 1]
        j = int(math.floor(j))

        if g == 0:
            return data[j]
        else:
            return data[j] + (data[j + 1] - data[j]) * (c + d * g)

    data = sorted(data)
    data_len = len(data)

    return [_get_quantile(q, data_len) for q in quantiles]


def try_import(packages):
    for package in packages:
        try:
            __import__(package)
        except ImportError:
            raise ImportError('You need to run pip install "%s"' % package)

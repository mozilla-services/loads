import datetime
import ujson as json    # NOQA
import json as _json
import logging
import logging.handlers
import os
import sys
import urlparse
import math
import fnmatch
import random
import zipfile
from cStringIO import StringIO
import hashlib

try:
    from gevent import socket as gevent_socket
except ImportError:
    gevent_socket = None


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

    formatter = logging.Formatter('[%(asctime)s][%(process)d] %(message)s')
    ch.setFormatter(formatter)
    logger_.addHandler(ch)

    # for the tests
    if 'TESTING' in os.environ:
        fh = logging.FileHandler('/tmp/loads.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)


def total_seconds(td):
    # works for 2.7 and 2.6
    diff = (td.seconds + td.days * 24 * 3600) * 10 ** 6
    return (td.microseconds + diff) / float(10 ** 6)


class DateTimeJSONEncoder(_json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.timedelta):
            return total_seconds(obj)
        else:
            return super(DateTimeJSONEncoder, self).default(obj)


def split_endpoint(endpoint):
    """Returns the scheme, the location, and maybe the port.
    """
    res = {}
    parts = urlparse.urlparse(endpoint)
    res['scheme'] = parts.scheme

    if parts.scheme == 'tcp':
        netloc = parts.netloc.rsplit(':')
        if len(netloc) == 1:
            netloc.append('80')
        res['ip'] = netloc[0]
        res['port'] = int(netloc[1])
    elif parts.scheme == 'ipc':
        res['path'] = parts.path
    else:
        raise NotImplementedError()

    return res


_DNS_CACHE = {}


def dns_resolve(url):
    """Resolve hostname in the given url, using cached results where possible.

    Given a url, this function does DNS resolution on the contained hostname
    and returns a 3-tuple giving:  the URL with hostname replace by IP addr,
    the original hostname string, and the resolved IP addr string.

    The results of DNS resolution are cached to make sure this doesn't become
    a bottleneck for the loadtest.  If the hostname resolves to multiple
    addresses then a random address is chosen.
    """
    parts = urlparse.urlparse(url)
    netloc = parts.netloc.rsplit(':')
    if len(netloc) == 1:
        netloc.append('80')

    original = netloc[0]
    addrs = _DNS_CACHE.get(original)
    if addrs is None:
        try:
            addrs = gevent_socket.gethostbyname_ex(original)[2]
        except AttributeError:
            # gethostbyname_ex was introduced by gevent 1.0,
            # fallback on gethostbyname instead.
            logger.info('gevent.socket.gethostbyname_ex is not present, '
                        'Falling-back on gevent.socket.gethostbyname')
            addrs = [gevent_socket.gethostbyname(original)]
        _DNS_CACHE[original] = addrs

    resolved = random.choice(addrs)
    netloc = resolved + ':' + netloc[1]
    parts = (parts.scheme, netloc) + parts[2:]
    return urlparse.urlunparse(parts), original, resolved


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

    # Depending how loads is ran, "" can or cannot be present in the path. This
    # adds it if it's missing.
    if len(sys.path) < 1 or sys.path[0] not in ('', os.getcwd()):
        sys.path.insert(0, '')

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


def get_quantiles(data, quantiles):
    """Computes the quantiles for the data array you pass along.

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

        if g == 0 or j == len(data) - 1:
            return data[j]
        else:
            return data[j] + (data[j + 1] - data[j]) * (c + d * g)

    data = sorted(data)
    data_len = len(data)

    return [_get_quantile(q, data_len) for q in quantiles]


def try_import(*packages):
    failed_packages = []
    for package in packages:
        try:
            __import__(package)
        except ImportError:
            failed_packages.append(package)
    if failed_packages:
        failed_packages = " ".join(failed_packages)
        raise ImportError('You need to run "pip install %s"' % failed_packages)


def glob(patterns, location='.'):
    for pattern in patterns:
        basedir, pattern = os.path.split(pattern)
        basedir = os.path.abspath(os.path.join(location, basedir))
        for file_ in os.listdir(basedir):
            if fnmatch.fnmatch(file_, pattern):
                yield os.path.join(basedir, file_)


def pack_include_files(include_files, location='.'):
    """Package up the specified include_files into a zipfile data bundle.

    This is a convenience function for packaging up data files into a binary
    blob, that can then be shipped to the different agents.  Unpack the files
    using unpack_include_files().
    """
    file_data = StringIO()
    zf = zipfile.ZipFile(file_data, "w", compression=zipfile.ZIP_DEFLATED)

    def store_file(name, filepath):
        info = zipfile.ZipInfo(name)
        info.external_attr = os.stat(filepath).st_mode << 16L
        with open(filepath) as f:
            zf.writestr(info, f.read())

    for basepath in glob(include_files, location):
        basedir, basename = os.path.split(basepath)
        if not os.path.isdir(basepath):
            store_file(basename, basepath)
        else:
            for root, dirnames, filenames in os.walk(basepath):
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    store_file(filepath[len(basedir):], filepath)

    zf.close()
    return file_data.getvalue().encode('base64')


def maybe_makedirs(dirpath):
    """Like os.makedirs, but not an error if the final directory exists."""
    if not os.path.isdir(dirpath):
        os.makedirs(dirpath)


def unpack_include_files(file_data, location='.'):
    """Unpackage a blob of include_files data into the specified directory.

    This is a convenience function for unpackaging data files from a binary
    blob, that can be used on the different agents.  It accepts data in the
    format produced by pack_include_files().
    """
    file_data = str(file_data).decode('base64')
    zf = zipfile.ZipFile(StringIO(file_data))

    for itemname in zf.namelist():
        itempath = os.path.join(location, itemname.lstrip("/"))
        if itemname.endswith("/"):
            maybe_makedirs(itempath)
        else:
            maybe_makedirs(os.path.dirname(itempath))
            with open(itempath, "w") as f:
                f.write(zf.read(itemname))
            mode = zf.getinfo(itemname).external_attr >> 16L
            if mode:
                os.chmod(itempath, mode)
    zf.close()


def null_streams(streams):
    """Set the given outputs to /dev/null to be sure we don't store their
    content in memory.

    This is useful when you want to spawn new processes and don't care about
    their outputs. The other approach, using subprocess.PIPE can slow down
    things and uses memory without any rationale.
    """
    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        for stream in streams:
            if not hasattr(stream, 'fileno'):
                # we're probably dealing with a file-like
                continue
            try:
                stream.flush()
                os.dup2(devnull, stream.fileno())
            except IOError:
                # some streams, like stdin - might be already closed.
                pass
    finally:
        os.close(devnull)


def dict_hash(data, omit_keys=None):
    """Useful to identify a data mapping.
    """
    if omit_keys is None:
        omit_keys = []

    hash = hashlib.md5()

    for key, value in data.items():
        if key in omit_keys:
            continue
        hash.update(str(key))
        hash.update(str(value))
        hash.update('ENDMARKER')

    return hash.hexdigest()


def seconds_to_time(seconds, loose=False):
    if seconds == 0:
        return 'Now.'

    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    res = []

    def _join():
        if len(res) == 1:
            return res[0]
        else:
            return '%s and %s.' % (' '.join(res[:-1]), res[-1])

    if days > 0:
        res.append('%d d' % days)
        if loose:
            return _join()
    if hours > 0:
        res.append('%d h' % hours)
        if loose:
            return _join()
    if minutes > 0:
        res.append('%d min' % minutes)
        if loose:
            return _join()

    if seconds > 0:
        res.append('%d sec' % seconds)

    return _join()


def unbatch(data):
    for field, messages in data['counts'].items():
        for message in messages:
            message['agent_id'] = data['agent_id']
            if 'run_id' in data:
                message['run_id'] = data['run_id']
            yield field, message

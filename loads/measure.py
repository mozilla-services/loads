import datetime

from requests.sessions import Session as _Session
from loads.stream import get_global_stream, set_global_stream
#from gevent.socket import gethostbyname
from socket import gethostbyname


import urlparse


def _measure(req):
    data = {'elapsed': req.elapsed,
            'started': req.started,
            'status': req.status_code,
            'url': req.url,
            'method': req.method,
            'cycle': req.current_cycle,
            'user': req.current_user}

    stream = get_global_stream()

    if stream is None:
        stream = set_global_stream('stdout')

    stream.push(data)


_CACHE = {}

def resolve(url):
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


class Session(_Session):

    def __init__(self, test):
        _Session.__init__(self)
        self.test = test

    def send(self, request, **kwargs):
        request.url, original, resolved = resolve(request.url)
        request.headers['Host'] = original

        # started
        start = datetime.datetime.utcnow()
        res = _Session.send(self, request, **kwargs)
        res.started = start
        res.method = request.method
        res.current_cycle = self.test.current_cycle
        res.current_user = self.test.current_user
        _measure(res)
        return res

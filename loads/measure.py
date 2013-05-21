import datetime
from requests.sessions import Session as _Session
from webtest.app import TestApp as _TestApp
from wsgiproxy import HostProxy
from wsgiproxy.requests_client import HttpClient

from loads.util import dns_resolve


class RequestsClient(HttpClient):
    # We need that while waiting upstream to be merged & released.
    # https://github.com/gawel/WSGIProxy2/pull/1/files

    default_options = dict(verify=False, allow_redirects=False)

    def __init__(self, session, chunk_size=1024 * 24, **requests_options):
        options = self.default_options.copy()
        options.update(requests_options)

        self.options = options
        self.chunk_size = chunk_size
        self.session = session

    def __call__(self, uri, method, body, headers):
        kwargs = self.options.copy()
        kwargs['headers'] = headers
        if 'Transfer-Encoding' in headers:
            del headers['Transfer-Encoding']
        if headers.get('Content-Length'):
            kwargs['data'] = body.read(int(headers['Content-Length']))
        response = self.session.request(method, uri, **kwargs)
        location = response.headers.get('location') or None
        status = '%s %s' % (response.status_code, response.reason)
        headers = [(k.title(), v) for k, v in response.headers.items()]
        return (status, location, headers,
                response.iter_content(chunk_size=self.chunk_size))


class TestApp(_TestApp):
    """A subclass of webtest.TestApp which uses the requests backend per
    default.
    """
    def __init__(self, app, session, stream, *args, **kwargs):
        self.session = session
        self.stream = stream

        client = RequestsClient(session=self.session)
        app = HostProxy(app, client=client)

        super(TestApp, self).__init__(app, *args, **kwargs)

    # XXX redefine here the _do_request, check_status and check_errors methods.
    # so we can actually use them to send information to the collector


class Session(_Session):
    """Extends Requests' Session object in order to send information to the
    streamer.
    """

    def __init__(self, test, stream):
        _Session.__init__(self)
        self.test = test
        self.stream = stream
        self.loads_status = None

    def send(self, request, **kwargs):
        """Do the actual request from within the session, doing some
        measures at the same time about the request (duration, status, etc).
        """
        request.url, original, resolved = dns_resolve(request.url)
        request.headers['Host'] = original

        # attach some information to the request object for later use.
        start = datetime.datetime.utcnow()
        res = _Session.send(self, request, **kwargs)
        res.started = start
        res.method = request.method
        self._analyse_request(res)
        return res

    def _analyse_request(self, req):
        """Analyse some information about the request and send the information
        to a stream.

        :param req: the request to analyse.
        """
        loads_status = self.loads_status or (None, None, None)
        data = {'elapsed': req.elapsed,
                'started': req.started,
                'status': req.status_code,
                'url': req.url,
                'method': req.method,
                'loads_status': list(loads_status)}

        self.stream.push('hit', data)

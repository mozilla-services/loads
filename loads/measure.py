import datetime
import urlparse
import os

from requests.sessions import Session as _Session, REDIRECT_STATI
from webtest.app import TestApp as _TestApp
from wsgiproxy.proxies import HostProxy as _HostProxy
from wsgiproxy.requests_client import HttpClient

from loads.util import dns_resolve


class TestApp(_TestApp):
    """A subclass of webtest.TestApp which uses the requests backend per
    default.
    """
    def __init__(self, app, session, test_result, *args, **kwargs):
        self.session = session
        self.test_result = test_result

        client = HttpClient(session=self.session)
        self.proxy = HostProxy(app, client=client)

        super(TestApp, self).__init__(self.proxy, *args, **kwargs)

    @property
    def server_url(self):
        return self.proxy.uri

    @server_url.setter
    def server_url(self, value):
        self.proxy.uri = value

    # XXX redefine here the _do_request, check_status and check_errors methods.
    # so we can actually use them to send information to the test_result


class HostProxy(_HostProxy):
    """A proxy to redirect all request to a specific uri"""

    def __init__(self, uri, *args, **kwargs):
        super(HostProxy, self).__init__(uri, *args, **kwargs)
        self._uri = None
        self.scheme = None
        self.net_loc = None
        self.uri = uri

    @property
    def uri(self):
        return self._uri

    @uri.setter
    def uri(self, value):
        self._uri = value.rstrip('/')
        self.scheme, self.net_loc = urlparse.urlparse(self.uri)[0:2]

    def extract_uri(self, environ):
        environ['HTTP_HOST'] = self.net_loc
        return self.uri


class Session(_Session):
    """Extends Requests' Session object in order to send information to the
    test_result.
    """

    def __init__(self, test, test_result, dns_resolve=True):
        _Session.__init__(self)
        self.verify = not os.getenv('BYPASS_SSL_CHECK')
        self.test = test
        self.test_result = test_result
        self.loads_status = None, None, None, None
        self.dns_resolve = dns_resolve

    def request(self, method, url, headers=None, **kwargs):
        if not url.startswith('https://') and self.dns_resolve:
            url, original, resolved = dns_resolve(url)
            if headers is None:
                headers = {}
            headers['Host'] = original
        return super(Session, self).request(
            method, url, headers=headers, **kwargs)

    def resolve_redirects(self, resp, req, stream=False, timeout=None,
                               verify=True, cert=None, proxies=None):
        """If there is a redirect, need to record information about the hit before
        it is obliterated by the next request."""
        # Future version of requests (some time > 2.2.1) has Response.is_redirect
        if 'location' in resp.headers and resp.status_code in REDIRECT_STATI:
            resp.started = self._started
            resp.method = req.method
            self._analyse_request(resp)
            req._needs_analysis = False
        return _Session.resolve_redirects(self, resp, req, stream=stream, timeout=timeout,
                                          verify=verify,cert=cert,proxies=proxies)

    def send(self, request, **kwargs):
        """Do the actual request from within the session, doing some
        measures at the same time about the request (duration, status, etc).
        """
        # If the request receives a redirect response code, collecting the
        # result will be handled by resolve_redirects() before the result
        # object is thrown away to perform the redirect. In that case, this
        # flag will be set to false, indicating that nothing needs to be
        # (or should be) recorded at the end of this method.
        request._needs_analysis = True
        # attach some information to the request object for later use.
        self._started = datetime.datetime.utcnow()
        res = _Session.send(self, request, **kwargs)
        if request._needs_analysis == True:
            res.started = self._started
            res.method = request.method
            self._analyse_request(res)
        return res

    def _analyse_request(self, req):
        """Analyse some information about the request and send the information
        to the test_result.

        :param req: the request to analyse.
        """
        if self.test_result is not None:
            self.test_result.add_hit(elapsed=req.elapsed,
                                     started=req.started,
                                     status=req.status_code,
                                     url=req.url,
                                     method=req.method,
                                     loads_status=self.loads_status)

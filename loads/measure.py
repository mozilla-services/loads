import datetime
from requests.sessions import Session as _Session
from loads.stream import get_global_stream, set_global_stream
from loads.util import dns_resolve


class Session(_Session):
    """Extends Requests' Session object in order to send information to the
    streamer.
    """

    def __init__(self, test):
        _Session.__init__(self)
        self.test = test
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

        stream = get_global_stream()

        if stream is None:
            stream = set_global_stream('stdout', {'total': 1})

        stream.push('hit', data)

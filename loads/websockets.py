import gevent
from collections import defaultdict

from ws4py.client.geventclient import WebSocketClient as _WS


_SOCKETS = defaultdict(list)


class WebSocketClient(_WS):
    def __init__(self, url, test_result, protocols=None, extensions=None,
                 callback=None):
        super(WebSocketClient, self).__init__(url, protocols, extensions)
        self.callback = callback
        self._test_result = test_result

    def received_message(self, m):
        self.callback(m)
        if self._test_result is not None:
            self._test_result.socket_message(len(m.data))
        super(WebSocketClient, self).received_message(m)

    def opened(self):
        if self._test_result is not None:
            self._test_result.socket_open()
        super(WebSocketClient, self).opened()

    def closed(self, code, reason):
        if self._test_result is not None:
            self._test_result.socket_close()
        super(WebSocketClient, self).closed(code, reason)


def cleanup(greenlet):
    for sock in _SOCKETS[id(greenlet)]:
        sock.close()


def create_ws(url, callback, test_result, protocols=None, extensions=None,
              klass=None):
    custom_klass = klass is not None
    if klass is None:
        klass = WebSocketClient

    socket = klass(url=url, test_result=test_result,
                   protocols=protocols, extensions=extensions,
                   callback=callback)

    socket.daemon = True
    if not custom_klass:
        current = gevent.getcurrent()
        # XXX sometimes I get greenlets objects, sometime Greenlets... ????
        if hasattr(current, 'link'):
            current.link(cleanup)

        current_id = id(current)
        socket.connect()
        _SOCKETS[current_id].append(socket)

    return socket

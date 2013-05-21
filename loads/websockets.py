import gevent
from collections import defaultdict

from ws4py.client.geventclient import WebSocketClient


_SOCKETS = defaultdict(list)


class WebSocketHook(WebSocketClient):
    def __init__(self, url, collector, protocols=None, extensions=None,
                 callback=None):
        super(WebSocketHook, self).__init__(url, protocols,
                                            extensions)
        self.callback = callback
        self._collector = collector

    def received_message(self, m):
        data = {'size': len(m.data)}
        self._collector.push('websocket-message', data)
        self.callback(m)

    def opened(self):
        self._collector.push('websocket-opened')
        super(WebSocketHook, self).opened()

    def closed(self, code, reason):
        self._collector.push('websocket-closed', code=code, reason=reason)
        super(WebSocketHook, self).closed(code, reason)


def cleanup(greenlet):
    for sock in _SOCKETS[id(greenlet)]:
        sock.close()


def create_ws(url, stream, callback, protocols=None, extensions=None):
    current = gevent.getcurrent()
    # XXX
    # sometimes I get greenlets objects, sometime Greenlets... ????
    if hasattr(current, 'link'):
        current.link(cleanup)
    current_id = id(current)
    socket = WebSocketHook(url, stream, protocols, extensions,
                           callback=callback)
    socket.daemon = True
    socket.connect()
    _SOCKETS[current_id].append(socket)
    return socket

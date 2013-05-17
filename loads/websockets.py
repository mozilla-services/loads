import gevent
from collections import defaultdict

from ws4py.client.geventclient import WebSocketClient
from loads.stream import get_global_stream, set_global_stream


_SOCKETS = defaultdict(list)


class WebSocketHook(WebSocketClient):
    def __init__(self, url, protocols=None, extensions=None,
                 callback=None):
        super(WebSocketHook, self).__init__(url, protocols,
                                            extensions)
        self.callback = callback
        self._stream = get_global_stream()

        if self._stream is None:
            self._stream = set_global_stream('stdout',
                                             {'stream_stdout_total': 1})

    def received_message(self, m):
        data = {'event': 'message', 'size': len(m.data)}
        self._stream.push('websocket', data)
        self.callback(m)

    def opened(self):
        data = {'event': 'opened'}
        self._stream.push('websocket', data)
        super(WebSocketHook, self).opened()

    def closed(self, code, reason):
        data = {'event': 'closed',
                'code': code,
                'reason': reason}
        self._stream.push('websocket', data)
        super(WebSocketHook, self).closed(code, reason)


def cleanup(greenlet):
    for sock in _SOCKETS[id(greenlet)]:
        sock.close()


def create_ws(url, callback, protocols=None, extensions=None):
    current = gevent.getcurrent()
    # XXX
    # sometimes I get greenlets objects, sometime Greenlets... ????
    if hasattr(current, 'link'):
        current.link(cleanup)
    current_id = id(current)
    socket = WebSocketHook(url, protocols, extensions, callback=callback)
    socket.daemon = True
    socket.connect()
    _SOCKETS[current_id].append(socket)
    return socket

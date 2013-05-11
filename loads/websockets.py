import gevent
from collections import defaultdict

from ws4py.client.threadedclient import WebSocketClient
from loads.stream import get_global_stream, set_global_stream


_SOCKETS = defaultdict(list)


class WebSocketHook(WebSocketClient):
    def __init__(self, url, protocols=None, extensions=None,
                 heartbeat_freq=None, callback=None):
        super(WebSocketHook, self).__init__(url, protocols,
                                            extensions,
                                            heartbeat_freq
                                            )
        self.callback = callback
        self._stream = get_global_stream()

        if self._stream is None:
            self._stream = set_global_stream('stdout',
                                             {'stream_stdout_total': 1})

    def received_message(self, m):
        data = {'websocket': {'event': 'message', 'size': len(m.data)}}
        self._stream.push(data)
        self.callback(m)

    def opened(self):
        data = {'websocket': {'event': 'opened'}}
        self._stream.push(data)
        super(WebSocketHook, self).opened()

    def closed(self, code, reason):
        data = {'websocket': {'event': 'closed',
                              'code': code,
                              'reason': reason}}
        self._stream.push(data)
        super(WebSocketHook, self).closed(code, reason)


def cleanup(greenlet):
    for sock in _SOCKETS[id(greenlet)]:
        sock.close()


def create_ws(url, callback, protocols=None, extensions=None):
    greenlet = gevent.getcurrent()
    greenlet.link(cleanup)
    current_id = id(greenlet)
    socket = WebSocketHook(url, protocols, extensions, callback=callback)
    socket.daemon = True
    socket.connect()
    _SOCKETS[current_id].append(socket)
    return socket

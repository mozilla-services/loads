import unittest2
from loads.websockets import WebSocketClient, create_ws


class TestWebSockets(unittest2.TestCase):

    def test_custom_klass(self):

        class WS(WebSocketClient):
            data = []

            def received_message(self, m):
                super(WS, self).received_message(m)
                self.data.append(m)

        ws = create_ws('ws://example.com', None, None, klass=WS)
        self.assertTrue(isinstance(ws, WS))

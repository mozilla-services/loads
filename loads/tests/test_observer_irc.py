import unittest2
import socket
import select
import os

from loads.observers import irc
from loads.tests.support import hush


_SOCKETS = []


def _select(*args):
    return _SOCKETS, [], []


class FakeSocket(object):

    _file = os.path.join(os.path.dirname(__file__), 'ircdata.txt')

    def __init__(self, *args, **kw):
        self.sent = []
        with open(self._file) as f:
            self.data = list(reversed(f.readlines()))

        _SOCKETS.append(self)

    def bind(self, *args):
        pass
    close = shutdown = connect = bind

    def send(self, data):
        self.sent.append(data)

    def recv(self, *args):
        if self.data == []:
            return ''
        return self.data.pop()


class TestIRC(unittest2.TestCase):

    def setUp(self):
        self.old = socket.socket
        socket.socket = FakeSocket
        self.old_select = select.select
        select.select = _select

    def tearDown(self):
        socket.socket = self.old
        select.select = self.old_select

    @hush
    def test_send(self):
        results = 'yeah'
        client = irc(ssl=False)
        client(results)

        # what did we send on IRC
        wanted = ['NICK loads',
                  'USER loads 0 * :loads',
                  'JOIN #services-dev',
                  'PRIVMSG #services-dev :[loads] Test Over. \x1fyeah',
                  'QUIT :Bye !',
                  'QUIT :Connection reset by peer']

        data = [line.strip('\r\n') for line in _SOCKETS[0].sent]
        self.assertEqual(data, wanted)

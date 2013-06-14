import tempfile
import os

from zmq.green.eventloop import ioloop


class BrokerDB(object):
    """A simple DB that's synced on disc every 500 ms
    """
    def __init__(self, loop, path=None):
        if path is None:
            fd, path = tempfile.mkstemp()
            os.close(fd)

        self.path = path
        self._file = open(path, 'a+')
        self._buffer = []
        self._callback = ioloop.PeriodicCallback(self.flush, 250, loop)
        self._callback.start()

    def add(self, data):
        self._buffer.append(data)

    def flush(self):
        if len(self._buffer) == 0:
            return
        self._file.write('\n'.join(self._buffer))
        self._buffer[:] = []

    def close(self):
        self._callback.stop()
        self._file.close()

    def get_data(self):
        # XXX stream it?
        with open(self.path) as f:
            return f.read().split()

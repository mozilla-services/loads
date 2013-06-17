import tempfile
import os
from collections import defaultdict
import json

from zmq.green.eventloop import ioloop


class BrokerDB(object):
    """A simple DB that's synced on disc eventually
    """
    def __init__(self, loop, directory=None, sync_delay=250):
        if directory is None:
            self.directory = tempfile.mkdtemp()
        else:
            self.directory = directory

        self._buffer = defaultdict(list)
        self.sync_delay = sync_delay
        self._callback = ioloop.PeriodicCallback(self.flush, self.sync_delay,
                                                 loop)
        self._callback.start()

    def add(self, data):
        self._buffer[data.get('run_id')].append(data)

    def flush(self):
        if len(self._buffer) == 0:
            return
        for run_id, data in self._buffer.items():
            if data == []:
                continue
            filename = os.path.join(self.directory, run_id)
            with open(filename, 'a+') as f:
                f.write('\n'.join([json.dumps(item) for item in data]))
        self._buffer.clear()

    def close(self):
        self._callback.stop()

    def get_data(self, run_id):
        # XXX stream it?
        filename = os.path.join(self.directory, run_id)
        with open(filename) as f:
            return f.read().split()

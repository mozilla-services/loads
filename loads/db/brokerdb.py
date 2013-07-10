import os
from collections import defaultdict
import json

from gevent.queue import Queue
from zmq.green.eventloop import ioloop


DEFAULT_DBDIR = os.path.join('/tmp', 'loads')


class BrokerDB(object):
    """A simple DB that's synced on disc eventually
    """
    def __init__(self, loop, directory, sync_delay=250):
        self.directory = directory
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

        self._buffer = defaultdict(Queue)
        self.sync_delay = sync_delay
        self._callback = ioloop.PeriodicCallback(self.flush, self.sync_delay,
                                                 loop)
        self._callback.start()
        self._counts = defaultdict(lambda: defaultdict(int))
        self._dirty = False
        self._metadata = defaultdict(dict)

    def save_metadata(self, run_id, metadata):
        self._metadata[run_id] = metadata

    def get_metadata(self, run_id):
        filename = os.path.join(self.directory, run_id + '-metadata.json')
        if os.path.exists(filename):
            with open(filename) as f:
                return json.load(f)
        else:
            return self._metadata[run_id]

    def add(self, data):
        run_id = data.get('run_id')
        data_type = data.get('data_type')
        self._counts[run_id][data_type] += 1
        self._buffer[run_id].put(data)
        self._dirty = True

    def flush(self):
        if len(self._buffer) == 0 or not self._dirty:
            return

        for run_id, queue in self._buffer.items():
            # lines
            qsize = queue.qsize()
            if qsize == 0:
                continue

            filename = os.path.join(self.directory, run_id)

            with open(filename, 'a+') as f:
                for i in range(qsize - 1):
                    json.dump(queue.get() + '\n', f)

            # counts
            filename = os.path.join(self.directory, run_id + '-counts.json')
            counts = dict(self._counts[run_id]).items()
            counts.sort()
            with open(filename, 'w') as f:
                json.dump(counts, f)

            # metadata
            filename = os.path.join(self.directory, run_id + '-metadata.json')
            with open(filename, 'w') as f:
                json.dump(self._metadata[run_id], f)

        self._dirty = False

    def close(self):
        self._callback.stop()

    def get_counts(self, run_id):
        filename = os.path.join(self.directory, run_id + '-counts.json')
        if os.path.exists(filename):
            with open(filename) as f:
                return json.load(f)
        else:
            return dict(self._counts[run_id])

    def get_data(self, run_id):
        filename = os.path.join(self.directory, run_id)
        if not os.path.exists(filename):
            raise StopIteration()
        else:
            with open(filename) as f:
                for line in f:
                    yield json.loads(line)

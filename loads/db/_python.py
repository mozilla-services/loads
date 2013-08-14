import os
from collections import defaultdict
import json

from gevent.queue import Queue
from zmq.green.eventloop import ioloop
from loads.db import BaseDB


DEFAULT_DBDIR = os.path.join('/tmp', 'loads')


class BrokerDB(BaseDB):
    """A simple DB that's synced on disc eventually
    """
    name = 'python'
    options = {'directory': (DEFAULT_DBDIR, 'DB path.', str),
               'sync_delay': (250, 'Sync delay', int)}

    def _initialize(self):
        self.directory = self.params['directory']
        self.sync_delay = self.params['sync_delay']

        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

        self._buffer = defaultdict(Queue)
        self._callback = ioloop.PeriodicCallback(self.flush, self.sync_delay,
                                                 self.loop)
        self._callback.start()
        self._counts = defaultdict(lambda: defaultdict(int))
        self._dirty = False
        self._metadata = defaultdict(dict)

    def update_metadata(self, run_id, **metadata):
        existing = self._metadata.get(run_id, {})
        existing.update(metadata)
        self._dirty = True
        self._metadata[run_id] = existing

    def save_metadata(self, run_id, metadata):
        self._metadata[run_id] = metadata
        self._dirty = True

    def get_metadata(self, run_id):
        self.flush()
        filename = os.path.join(self.directory, run_id + '-metadata.json')
        if not os.path.exists(filename):
            return {}

        with open(filename) as f:
            return json.load(f)

    def add(self, data):
        run_id = data.get('run_id')
        data_type = data.get('data_type', 'unknown')
        size = data.get('size', 1)
        self._counts[run_id][data_type] += size
        self._buffer[run_id].put(data)
        self._dirty = True

    def flush(self):
        if not self._dirty:
            return

        # saving metadata files
        for run_id in self._metadata:
            # metadata
            filename = os.path.join(self.directory, run_id + '-metadata.json')
            with open(filename, 'w') as f:
                json.dump(self._metadata[run_id], f)

        if len(self._buffer) == 0:
            return

        for run_id, queue in self._buffer.items():
            # lines
            qsize = queue.qsize()
            if qsize == 0:
                continue

            if run_id is None:
                run_id = 'unknown'

            filename = os.path.join(self.directory, run_id + '-db.json')

            with open(filename, 'a+') as f:
                for i in range(qsize):
                    line = queue.get()
                    f.write(json.dumps(line, sort_keys=True) + '\n')

            # counts
            filename = os.path.join(self.directory, run_id + '-counts.json')
            counts = dict(self._counts[run_id]).items()
            counts.sort()
            with open(filename, 'w') as f:
                json.dump(counts, f)

        self._dirty = False

    def close(self):
        self._callback.stop()

    def get_counts(self, run_id):
        self.flush()
        filename = os.path.join(self.directory, run_id + '-counts.json')

        if not os.path.exists(filename):
            return {}

        with open(filename) as f:
            return json.load(f)

    def get_runs(self):
        return set([path[:-len('-db.json')]
                    for path in os.listdir(self.directory)
                    if path.endswith('-db.json')])

    def get_data(self, run_id, data_type=None, groupby=False):
        self.flush()
        filename = os.path.join(self.directory, run_id + '-db.json')

        if not os.path.exists(filename):
            raise StopIteration()

        if not groupby:
            with open(filename) as f:
                for line in f:
                    data = json.loads(line)
                    filtered = (data_type is not None and
                                data_type != data.get('data_type'))
                    if filtered:
                        continue
                    yield data
        else:
            grouped = defaultdict(int)
            with open(filename) as f:
                for line in f:
                    data = json.loads(line)
                    filtered = (data_type is not None and
                                data_type != data.get('data_type'))
                    if filtered:
                        continue

                    grouped[line] += 1

            for data, count in grouped.items():
                data = json.loads(data)
                data['count'] = count
                yield data

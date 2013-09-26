import zlib
import os
from collections import defaultdict

from gevent.queue import Queue
from zmq.green.eventloop import ioloop
from loads.db import BaseDB
from loads.util import json


DEFAULT_DBDIR = os.path.join('/tmp', 'loads')
ZLIB_START = 'x\x9c'
ZLIB_END = 'x\x8c'


def read_zfile(filename):
    remaining = ''

    with open(filename, 'rb') as f:
        while True:
            data = remaining + f.read(1024)
            if not data:
                raise StopIteration()

            size = len(data)
            pos = 0

            while pos < size:
                # grabbing a record
                rstart = data.find(ZLIB_START, pos)
                rend = data.find(ZLIB_END, rstart+1)

                if rend == -1 or rstart == rend:
                    # not a full record
                    break

                line = data[rstart:rend]
                if not line:
                    break

                try:
                    line = zlib.decompress(line)
                except zlib.error:
                    raise ValueError(line)

                record = json.loads(line)
                yield record, line

                pos = rend + len(ZLIB_END)

            if pos < size:
                remaining = data[pos:]
            else:
                remaining = ''


class BrokerDB(BaseDB):
    """A simple DB that's synced on disc eventually
    """
    name = 'python'
    options = {'directory': (DEFAULT_DBDIR, 'DB path.', str),
               'sync_delay': (2000, 'Sync delay', int)}

    def _initialize(self):
        self.directory = self.params['directory']
        self.sync_delay = self.params['sync_delay']

        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

        self._buffer = defaultdict(Queue)
        self._errors = defaultdict(Queue)
        self._callback = ioloop.PeriodicCallback(self.flush, self.sync_delay,
                                                 self.loop)
        self._callback.start()
        self._counts = defaultdict(lambda: defaultdict(int))
        self._dirty = False
        self._metadata = defaultdict(dict)
        self._urls = defaultdict(lambda: defaultdict(int))

    def ping(self):
        return True

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
        run_id = data['run_id']
        data_type = data.get('data_type', 'unknown')
        self._counts[run_id][data_type] += data.get('size', 1)
        self._buffer[run_id].put(dict(data))

        if 'url' in data:
            self._urls[run_id][data['url']] += 1

        if data_type == 'addError':
            self._errors[run_id].put(dict(data))

        self._dirty = True

    def _dump_queue(self, run_id, queue, filename):
        # lines
        qsize = queue.qsize()
        if qsize == 0:
            return

        if run_id is None:
            run_id = 'unknown'

        with open(filename, 'ab+') as f:
            for i in range(qsize):
                line = queue.get()
                if 'run_id' not in line:
                    line['run_id'] = run_id
                f.write(zlib.compress(json.dumps(line)) + ZLIB_END)

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

        for run_id, queue in self._errors.items():
            # error lines
            filename = os.path.join(self.directory, run_id + '-errors.json')
            self._dump_queue(run_id, queue, filename)

        for run_id, queue in self._buffer.items():
            # all lines
            filename = os.path.join(self.directory, run_id + '-db.json')
            self._dump_queue(run_id, queue, filename)

            # counts
            filename = os.path.join(self.directory, run_id + '-counts.json')
            counts = dict(self._counts[run_id])
            with open(filename, 'w') as f:
                json.dump(counts, f)

            # urls
            filename = os.path.join(self.directory, run_id + '-urls.json')
            with open(filename, 'w') as f:
                json.dump(self._urls[run_id], f)

        self._dirty = False

    def close(self):
        self._callback.stop()

    def get_urls(self, run_id):
        self.flush()
        filename = os.path.join(self.directory, run_id + '-urls.json')

        if not os.path.exists(filename):
            return {}

        with open(filename) as f:
            return json.load(f)

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

    def _batch(self, filename, start=None, size=None, filter=None):
        if start is not None and size is not None:
            end = start + size
        else:
            end = None

        # XXX suboptimal iterates until start is reached.
        sent = 0
        current = 0

        for current, (record, line) in enumerate(read_zfile(filename)):
            # filtering
            if filter is not None and filter(record):
                continue
            if start is not None and current < start:
                continue
            elif end is not None and current > end or sent == size:
                raise StopIteration()

            yield record, line

            sent += 1

    def get_errors(self, run_id, start=None, size=None):
        if size is not None and start is None:
            start = 0

        self.flush()
        filename = os.path.join(self.directory, run_id + '-errors.json')

        if not os.path.exists(filename):
            raise StopIteration()

        for data, line in self._batch(filename, start, size):
            yield data

    def get_data(self, run_id, data_type=None, groupby=False, start=None,
                 size=None):
        if size is not None and start is None:
            start = 0

        self.flush()
        filename = os.path.join(self.directory, run_id + '-db.json')

        if not os.path.exists(filename):
            raise StopIteration()

        def _filtered(data):
            return (data_type is not None and
                    data_type != data.get('data_type'))

        if not groupby:
            for data, line in self._batch(filename, start, size, _filtered):
                yield data
        else:
            grouped = dict()

            for data, line in self._batch(filename, start, size, _filtered):
                if line in grouped:
                    grouped[line] = grouped[line][0] + 1, data
                else:
                    grouped[line] = 1, data

            for count, data in grouped.values():
                data['count'] = count
                yield data

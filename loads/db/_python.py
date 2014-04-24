import zlib
import os
from collections import defaultdict

from gevent.queue import Queue
from zmq.green.eventloop import ioloop
from loads.db import BaseDB
from loads.util import json, dict_hash


DEFAULT_DBDIR = os.path.join('/tmp', 'loads')
ZLIB_START = 'x\x9c'
ZLIB_END = 'x\x8c'
GIGA = 1024. * 1024. * 1024.


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


def get_dir_size(path):
    """Returns directory size in gigabytes
    """
    total_size = 0.
    for dirpath, dirnames, filenames in os.walk(path):
        for file_ in filenames:
            fp = os.path.join(dirpath, file_)
            total_size += os.path.getsize(fp)
    return total_size / GIGA


class BrokerDB(BaseDB):
    """A simple DB that's synced on disc eventually
    """
    name = 'python'
    options = {'directory': (DEFAULT_DBDIR, 'DB path.', str),
               'sync_delay': (2000, 'Sync delay', int),
               'max_size': (-1, 'Max Size in Gigabytes', float)}

    def _initialize(self):
        self.directory = self.params['directory']
        self.sync_delay = self.params['sync_delay']
        self.max_size = self.params['max_size']

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
        self._headers = defaultdict(dict)
        self._key_headers = defaultdict(dict)

    def ping(self):
        return True

    def _update_headers(self, run_id):
        filename = os.path.join(self.directory, run_id + '-headers.json')
        if os.path.exists(filename):
            with open(filename) as f:
                headers = json.load(f)
            # int keys are saved as strings in json
            # so we need to convert them back
            headers = dict([(int(key), value)
                            for key, value in headers.items()])
            self._headers[run_id].update(headers)

            for key, value in self._headers[run_id].items():
                self._key_headers[run_id][value] = key

    def _compress_headers(self, run_id, data):
        result = {}
        headers = self._headers[run_id]

        for key, value in data.items():
            if key not in self._key_headers[run_id]:
                self._dirty = True
                compressed_keys = headers.keys()
                if len(compressed_keys) == 0:
                    next_compressed_key = 0
                else:
                    compressed_keys.sort()
                    next_compressed_key = compressed_keys[-1] + 1

                self._headers[run_id][next_compressed_key] = key
                self._key_headers[run_id][key] = next_compressed_key
                key = next_compressed_key
            else:
                key = self._key_headers[run_id][key]

            result[key] = value

        return result

    def _uncompress_headers(self, run_id, data):
        result = {}
        for key, value in data.items():
            result[self._headers[run_id][int(key)]] = value
        return result

    def update_metadata(self, run_id, **metadata):
        existing = self._metadata.get(run_id, {})

        # reload existing file if any
        if existing == {}:
            filename = os.path.join(self.directory, run_id + '-metadata.json')
            if os.path.exists(filename):
                with open(filename) as f:
                    existing = json.load(f)

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
        self.update_metadata(run_id, has_data=1)
        data_type = data.get('data_type', 'unknown')
        self._counts[run_id][data_type] += data.get('size', 1)
        self._buffer[run_id].put(dict(data))

        if 'url' in data:
            self._urls[run_id][data['url']] += 1

        if data_type == 'addError':
            self._errors[run_id].put(dict(data))

        self._dirty = True

    def _dump_queue(self, run_id, queue, filename, compress=True):
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
                line = self._compress_headers(run_id, line)
                if compress:
                    f.write(zlib.compress(json.dumps(line)) + ZLIB_END)
                else:
                    f.write(json.dumps(line) + '\n')

    def prepare_run(self):
        if self.max_size == -1:
            return
        current_size = get_dir_size(self.directory)
        runs = self.get_runs()
        if current_size >= self.max_size:
            # we need to wipe up older runs until we have enough space
            for run_id in runs:
                self.delete_run(run_id)
                if get_dir_size(self.directory) < self.max_size:
                    return

    def delete_run(self, run_id):
        for suffix in ('metadata', 'errors', 'db', 'counts', 'urls',
                       'headers'):

            filename = os.path.join(self.directory,
                                    '%s-%s.json' % (run_id, suffix))
            if os.path.exists(filename):
                os.remove(filename)

        for mapping in (self._counts, self._metadata, self._urls,
                        self._headers, self._key_headers):
            if run_id in mapping:
                del mapping[run_id]

    def is_summarized(self, run_id):
        db = os.path.join(self.directory, '%s-db.json' % run_id)
        meta = os.path.join(self.directory, '%s-metadata.json' % run_id)
        return os.path.exists(meta) and not os.path.exists(db)

    def summarize_run(self, run_id):
        # we just remove the -db file
        # XXX in the future we'll want to move it to another
        # storage so we keep the details.
        filename = os.path.join(self.directory,
                                '%s-db.json' % run_id)
        if os.path.exists(filename):
            os.remove(filename)

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
            self._dump_queue(run_id, queue, filename, compress=False)

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

            # headers
            filename = os.path.join(self.directory, run_id + '-headers.json')
            with open(filename, 'w') as f:
                json.dump(self._headers[run_id], f)

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
        runs = []
        for path in os.listdir(self.directory):
            if path.endswith('-metadata.json'):
                creat_ = os.stat(os.path.join(self.directory, path)).st_mtime
                runs.append((creat_, path))

        # from older to newer...
        runs.sort()
        return [path[:-len('-metadata.json')] for created, path in runs]

    def _batch(self, filename, start=None, size=None, filter=None,
               run_id=None, decompress=True):
        if start is not None and size is not None:
            end = start + size
        else:
            end = None

        # XXX suboptimal iterates until start is reached.
        sent = 0
        current = 0

        def _reader():
            if decompress:
                for record, line in read_zfile(filename):
                    yield record, line
            else:
                with open(filename, 'rb') as f:
                    for line in f:
                        yield json.loads(line), line

        for current, (record, line) in enumerate(_reader()):
            record = self._uncompress_headers(run_id, record)

            # filtering
            if filter is not None and filter(record):
                continue
            if start is not None and current < start:
                continue
            elif end is not None and current > end or sent == size:
                raise StopIteration()

            yield record

            sent += 1

    def get_errors(self, run_id, start=None, size=None):
        if size is not None and start is None:
            start = 0

        self.flush()
        filename = os.path.join(self.directory, run_id + '-errors.json')

        if not os.path.exists(filename):
            raise StopIteration()

        self._update_headers(run_id)

        for data in self._batch(filename, start, size, run_id=run_id,
                                decompress=False):
            yield data

    def get_data(self, run_id, data_type=None, groupby=False, start=None,
                 size=None):
        if size is not None and start is None:
            start = 0

        self.flush()
        filename = os.path.join(self.directory, run_id + '-db.json')

        if not os.path.exists(filename):
            raise StopIteration()

        self._update_headers(run_id)

        def _filtered(data):
            return (data_type is not None and
                    data_type != data.get('data_type'))

        if not groupby:
            for data in self._batch(filename, start, size, _filtered,
                                    run_id=run_id):
                yield data
        else:

            result = {}

            for data in self._batch(filename, start, size, _filtered,
                                    run_id=run_id):
                data_hash = dict_hash(data, ['count'])
                if data_hash in result:
                    result[data_hash]['count'] += 1
                else:
                    data['count'] = 1
                    result[data_hash] = data

            for data in result.values():
                yield data

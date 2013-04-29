import sys
import json
import datetime


_STREAM = None
_STREAMS = {}


def get_global_stream():
    return _STREAM


def set_global_stream(kind, **args):
    global _STREAM
    if kind not in _STREAMS:
        raise NotImplementedError(kind)

    _STREAM = _STREAMS[kind](**args)
    return _STREAM


def register_stream(klass):
    _STREAMS[klass.name] = klass


class NullStream(object):
    name = 'null'

    def __init__(self, **options):
        pass

    def push(self, data):
        pass

register_stream(NullStream)


class DateTimeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.timedelta):
            return obj.seconds, obj.microseconds
        else:
            return super(DateTimeJSONEncoder, self).default(obj)


class FileStream(object):
    name = 'file'

    def __init__(self, filename='/tmp/testing'):
        self.current = 0
        self.filename = filename
        self.encoder = DateTimeJSONEncoder()

    def push(self, data):
        with open(self.filename, 'a+') as f:
            f.write(self.encoder.encode(data) + '\n')


register_stream(FileStream)


class StdStream(object):
    name = 'stdout'

    def __init__(self, total):
        self.current = 0
        self.total = total

    def push(self, data):
        self.current += 1
        percent = int(float(self.current) / float(self.total) * 100.)
        bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
        sys.stdout.write("\r%s  %d%%" % (bar, percent))
        sys.stdout.flush()

register_stream(StdStream)

import sys
import json
import datetime
from unittest import TestResult

import zmq.green as zmq


_STREAM = None
_STREAMS = {}


def get_global_stream():
    return _STREAM


def set_global_stream(kind, args):
    global _STREAM
    if kind not in _STREAMS:
        raise NotImplementedError(kind)

    _STREAM = _STREAMS[kind](args)
    return _STREAM


def register_stream(klass):
    _STREAMS[klass.name] = klass


def stream_list():
    return _STREAMS.values()


class NullStream(object):
    name = 'null'
    options = {}

    def __init__(self, args):
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
    options = {'filename': ('Filename', str, None, True)}

    def __init__(self, args):
        self.current = 0
        self.filename = args['stream_file_filename']
        self.encoder = DateTimeJSONEncoder()

    def push(self, data):
        with open(self.filename, 'a+') as f:
            f.write(self.encoder.encode(data) + '\n')


register_stream(FileStream)


class StdStream(object):
    name = 'stdout'
    options = {'total': ('Total Number of items', int, None, False)}

    def __init__(self, args):
        self.current = 0
        self.total = args['stream_stdout_total']
        self.start = None
        self.end = None

    def push(self, data):
        date = data['started']
        if self.start is None:
            self.start = self.end = date
        else:
            if date < self.start:
                self.start = date
            elif date > self.end:
                self.end = date
        self.current += 1
        percent = int(float(self.current) / float(self.total) * 100.)
        bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
        sys.stdout.write("\r%s %d%%" % (bar, percent))

        if self.current == self.total:
            seconds = (self.end - self.start).total_seconds()
            if seconds == 0:
                rps = self.total
            else:
                rps = float(self.total) / seconds
            sys.stdout.write("\nHits: %d" % self.total)
            sys.stdout.write("\nStarted: %s" % self.start)
            sys.stdout.write("\nDuration: %.2f seconds" % seconds)
            sys.stdout.write("\nApproximate Average RPS: %d\n" % rps)

        sys.stdout.flush()


register_stream(StdStream)


class ZMQStream(object):
    name = 'zmq'
    options = {'endpoint': ('Socket to send the results to',
                            str, 'tcp://127.0.0.1:5558', True)}

    def __init__(self, args):
        self.context = zmq.Context()
        self._push = self.context.socket(zmq.PUSH)
        self._push.connect(args['stream_zmq_endpoint'])
        self.encoder = DateTimeJSONEncoder()
        self._result = TestResult()
        self.errors = []
        self.failures = []

    # unittest.TestResult APIS
    def startTest(self, test):
        pass
    stopTest = startTest

    def addFailure(self, test, failure):
        exc_info = self._result._exc_info_to_string(failure, test)
        self.failures.append((test, exc_info))
        self.push({'failure': exc_info})

    def addError(self, test, error):
        exc_info = self._result._exc_info_to_string(error, test)
        self.errors.append((test, exc_info))
        self.push({'error': exc_info})

    def addSuccess(self, test):
        pass

    def push(self, data):
        self._push.send(self.encoder.encode(data), zmq.NOBLOCK)


register_stream(ZMQStream)

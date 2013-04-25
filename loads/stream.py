import sys


_STREAM = None


def get_global_stream():
    return _STREAM


def set_global_stream(kind, **args):
    global _STREAM
    # XXX should create plugins
    if kind == 'stdout':
        _STREAM = StdStream(**args)
    elif kind == 'null':
        _STREAM = NullStream(**args)
    else:
        raise NotImplementedError(kind)
    return _STREAM


class NullStream(object):
    def __init__(self, **options):
        pass

    def push(self, data):
        pass


class StdStream(object):
    def __init__(self, total):
        self.current = 0
        self.total = total

    def push(self, data):
        self.current += 1
        percent = int(float(self.current) / float(self.total) * 100.)
        bar = '[' + '=' * percent + ' ' * (100 - percent) + ']'
        sys.stdout.write("\r%s  %d%%" % (bar, percent))
        sys.stdout.flush()

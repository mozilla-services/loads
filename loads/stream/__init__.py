

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


# register our own plugins
from null import NullStream
from _file import FileStream
from _zmq import ZMQStream
from std import StdStream

for stream in (NullStream, FileStream, ZMQStream, StdStream):
    register_stream(stream)

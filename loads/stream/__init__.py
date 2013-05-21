_STREAMS = {}


def create_stream(kind, args):
    if kind not in _STREAMS:
        raise NotImplementedError(kind)

    return _STREAMS[kind](args)


def register_stream(klass):
    _STREAMS[klass.name] = klass


def stream_list():
    return _STREAMS.values()


# register our own plugins
from null import NullStream
from _file import FileStream
from _zmq import ZMQStream
from std import StdStream
from collector import StreamCollector

for stream in (NullStream, FileStream, ZMQStream, StdStream, StreamCollector):
    register_stream(stream)

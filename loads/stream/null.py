class NullStream(object):
    """A streamer that's just consuming whatever you sent to it, but does
    nohting with it.
    """
    name = 'null'
    options = {}

    def __init__(self, args):
        pass

    def flush(self):
        pass

    def push(self, data_type, data):
        pass

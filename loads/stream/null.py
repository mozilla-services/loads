class NullStream(object):
    """A streamer that's just consuming whatever you sent to it, but does
    nohting with it.
    """
    name = 'null'
    options = {}

    def __init__(self, args):
        pass

    def push(self, data):
        pass

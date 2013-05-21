class NullOutput(object):
    """A very useless output, silenting everything."""
    name = 'null'
    options = {}

    def __init__(self, args):
        pass

    def flush(self):
        pass

    def push(self, data_type, data):
        pass

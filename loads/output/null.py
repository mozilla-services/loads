class NullOutput(object):
    """A very useless output, silenting everything."""
    name = 'null'
    options = {}

    def __init__(self, test_result, args):
        pass

    def flush(self):
        pass

    def push(self, method_called, *args, **data):
        pass

from loads.util import DateTimeJSONEncoder


class FileOutput(object):
    """A output writing to a file."""
    name = 'file'
    options = {'filename': ('Filename', str, None, True)}

    def __init__(self, test_result, args):
        self.test_result = test_result
        self.current = 0
        self.filename = args['output_file_filename']
        self.encoder = DateTimeJSONEncoder()
        self.fd = open(self.filename, 'a+')

    def push(self, method, **data):
        pass

    # XXX replace by an atexit
    def __del__(self):
        self.fd.close()

    def flush(self):
        # XXX Read what's in the test_result and build a report with it.
        raise NotImplemented()

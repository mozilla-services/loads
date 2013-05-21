from loads.util import DateTimeJSONEncoder


class FileOutput(object):
    """A output writing to a file."""
    name = 'file'
    options = {'filename': ('Filename', str, None, True)}

    def __init__(self, args):
        self.current = 0
        self.filename = args['output_file_filename']
        self.encoder = DateTimeJSONEncoder()
        self.fd = open(self.filename, 'a+')

    def push(self, data_type, data):
        self.fd.write(self.encoder.encode('%s %s' % (data_type, data)) + '\n')

    # XXX replace by an atexit
    def __del__(self):
        self.fd.close()

    def flush(self):
        pass

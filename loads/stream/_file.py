from loads.util import DateTimeJSONEncoder


class FileStream(object):
    """A streamer that writes everything you push to it to a file."""
    name = 'file'
    options = {'filename': ('Filename', str, None, True)}

    def __init__(self, args):
        self.current = 0
        self.filename = args['stream_file_filename']
        self.encoder = DateTimeJSONEncoder()
        self.fd = open(self.filename, 'a+')

    def push(self, data):
        self.fd.write(self.encoder.encode(data) + '\n')

    def __del__(self):
        self.fd.close()

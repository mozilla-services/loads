from loads.util import DateTimeJSONEncoder


class FileStream(object):
    name = 'file'
    options = {'filename': ('Filename', str, None, True)}

    def __init__(self, args):
        self.current = 0
        self.filename = args['stream_file_filename']
        self.encoder = DateTimeJSONEncoder()

    def push(self, data):
        with open(self.filename, 'a+') as f:
            f.write(self.encoder.encode(data) + '\n')

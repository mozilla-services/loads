""" Message class.
"""
from loads.util import json


class Message(object):

    def __init__(self, **data):
        self.data = data

    def __str__(self):
        return 'Message(%s)' % self.serialize()

    def serialize(self):
        return json.dumps(self.data)

    @classmethod
    def load_from_string(cls, data):
        return cls(**json.loads(data))

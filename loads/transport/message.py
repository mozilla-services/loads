""" Message class.
"""
from loads.util import json


class Message(object):

    def __init__(self, **data):
        self.data = data

    def serialize(self):
        return json.dumps(self.data)

    @classmethod
    def load_from_string(cls, data):
        return cls(**json.loads(data))

import unittest2
from loads.transport.message import Message
from loads.util import json


class TestMessage(unittest2.TestCase):

    def test_message(self):
        data = {'1': 2}
        msg = Message(**data)
        self.assertEquals(msg.serialize(), json.dumps(data))

        msg = Message.load_from_string(json.dumps(data))
        self.assertEquals(msg.serialize(), json.dumps(data))

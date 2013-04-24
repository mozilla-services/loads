# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import unittest
from loads.message import Message


class TestMessage(unittest.TestCase):

    def test_message(self):
        message = Message(one=1)
        data = message.serialize()
        message2 = Message.load_from_string(data)
        self.assertTrue(message.data, message2.data)

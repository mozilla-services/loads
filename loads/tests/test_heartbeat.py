# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import unittest
import time
from loads.transport.heartbeat import Stethoscope, Heartbeat


class TestHeartbeat(unittest.TestCase):

    def test_working(self):
        beats = []
        lost = []

        def onbeat():
            beats.append('.')

        def onbeatlost():
            lost.append('.')

        hb = Heartbeat('ipc:///tmp/stetho.ipc', interval=0.1)
        hb.start()
        time.sleep(.2)

        stetho = Stethoscope('ipc:///tmp/stetho.ipc', onbeat=onbeat,
                             onbeatlost=onbeatlost, delay=1., retries=5.)
        stetho.start()

        time.sleep(5.)

        stetho.stop()
        hb.stop()
        self.assertEqual(len(lost),  0, len(lost))
        self.assertTrue(len(beats) > 10, len(beats))

    def test_lost(self):
        beats = []
        lost = []

        def _onbeat():
            beats.append('.')

        def _onbeatlost():
            lost.append('.')

        hb = Heartbeat('ipc:///tmp/stetho.ipc', interval=0.1)
        hb.start()
        time.sleep(.2)

        stetho = Stethoscope('ipc:///tmp/stetho.ipc', onbeat=_onbeat,
                             onbeatlost=_onbeatlost, delay=0.1)
        stetho.start()

        time.sleep(2.)
        hb.stop()         # the hber stops

        # the stethoer continues for a while
        time.sleep(2.)

        stetho.stop()

        self.assertTrue(len(beats) > 0)
        self.assertTrue(len(lost) > 3)

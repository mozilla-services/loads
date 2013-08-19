# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import unittest2
from zmq.green.eventloop import ioloop
from loads.transport.heartbeat import Stethoscope, Heartbeat


class TestHeartbeat(unittest2.TestCase):

    def test_working(self):
        loop = ioloop.IOLoop()
        beats = []
        lost = []

        def onbeat():
            beats.append('.')

        def onbeatlost():
            lost.append('.')

        hb = Heartbeat('ipc:///tmp/stetho.ipc', interval=0.1,
                       io_loop=loop)
        stetho = Stethoscope('ipc:///tmp/stetho.ipc', onbeat=onbeat,
                             onbeatlost=onbeatlost, delay=1.,
                             retries=5., io_loop=loop)

        def start():
            hb.start()

        def start_2():
            stetho.start()
            # it's ok to try to start it again
            stetho.start()

        # hb starts immediatly
        loop.add_callback(start)

        # stetho 0.2 seconds after
        cb = ioloop.DelayedCallback(start_2, 200, io_loop=loop)
        cb.start()

        def stop():
            hb.stop()
            stetho.stop()
            loop.stop()

        # all stops after 1s
        cb = ioloop.DelayedCallback(stop, 1000, io_loop=loop)
        cb.start()

        # let's go
        loop.start()

        self.assertEqual(len(lost),  0, len(lost))
        self.assertTrue(len(beats) > 2, len(beats))

    def test_lost(self):
        beats = []
        lost = []
        loop = ioloop.IOLoop()

        def _hbreg():
            beats.append('o')

        def _onregister():
            beats.append('+')

        def _onbeat():
            beats.append('.')

        def _onbeatlost():
            lost.append('.')

        hb = Heartbeat('ipc:///tmp/stetho.ipc', interval=0.1,
                       io_loop=loop, onregister=_hbreg)

        stetho = Stethoscope('ipc:///tmp/stetho.ipc', onbeat=_onbeat,
                             onbeatlost=_onbeatlost, delay=0.1,
                             io_loop=loop, onregister=_onregister)

        # scenario
        def start():
            hb.start()
            stetho.start()

        def stop_hb():
            hb.stop()

        def stop_st():
            stetho.stop()
            loop.stop()

        loop.add_callback(start)

        # the hb stops after 500ms
        cb = ioloop.DelayedCallback(stop_hb, 500, io_loop=loop)
        cb.start()

        # the st stops after 1 second, then the loop
        cb = ioloop.DelayedCallback(stop_st, 1500, io_loop=loop)
        cb.start()
        loop.start()

        self.assertTrue(len(beats) > 0)
        self.assertEqual(beats[:2], ['o', '+'])
        self.assertTrue(len(lost) > 3)

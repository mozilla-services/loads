# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import unittest2
import time

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
        loop.add_timeout(time.time() + .2, start_2)

        def stop():
            hb.stop()
            stetho.stop()
            loop.stop()

        # all stops after 1s
        loop.add_timeout(time.time() + 1., stop)

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
                             io_loop=loop, onregister=_onregister,
                             warmup_delay=0)

        # scenario
        def start():
            hb.start()
            stetho.start()

        def stop_hb():
            hb.stop()

        def stop_st():
            stetho.stop()
            loop.stop()

        # that starts the heartbeat and the client
        loop.add_callback(start)

        # the hb stops after 500ms
        loop.add_timeout(time.time() + .5, stop_hb)

        # the st stops after 1 second, then the loop
        loop.add_timeout(time.time() + 1., stop_st)

        loop.start()

        self.assertTrue(len(beats) > 0)
        self.assertEqual(beats[:2], ['o', '+'])
        self.assertTrue(len(lost) > 0)

    def test_restart(self):
        # we want to make sure the Stethoscope can be restarted
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
                             io_loop=loop, onregister=_onregister,
                             warmup_delay=0)

        # scenario
        def start():
            hb.start()
            stetho.start()

        def stop_st():
            stetho.stop()

        def restart_st():
            stetho.start()
            beats.append('RESTARTED')

        def stop():
            stetho.stop()
            loop.stop()

        # that starts the heartbeat and the client
        loop.add_callback(start)

        # the st stops after 500ms
        loop.add_timeout(time.time() + .5, stop_st)

        # the st starts again after 500ms
        loop.add_timeout(time.time() + .5, restart_st)

        # the st stops after 1 second, then the loop
        loop.add_timeout(time.time() + 1., stop)
        loop.start()

        self.assertTrue(len(beats) > 0)
        self.assertTrue('RESTARTED' in beats)

        # make sure the st gets the beats after a restart
        rest = beats.index('RESTARTED')
        self.assertTrue('o+' in ''.join(beats[rest:]), beats)

import unittest
import os
from tempfile import mkstemp

import zmq
import gevent

from loads import util
from loads.util import resolve_name, set_logger, logger, dns_resolve
from loads.transport.util import (register_ipc_file, _cleanup_ipc_files, send,
                                  TimeoutError, recv, decode_params,
                                  dump_stacks)


class _BadSocket(object):

    def __init__(self, error):
        self.error = error

    def send(self, msg, *args):
        err = zmq.ZMQError()
        err.errno = self.error
        raise err

    def recv(self, *args):
        err = zmq.ZMQError()
        err.errno = self.error
        raise err


class TestUtil(unittest.TestCase):

    def test_resolve(self):

        ob = resolve_name('loads.tests.test_util.TestUtil')
        self.assertTrue(ob is TestUtil)

        ob = resolve_name('loads.tests.test_util:TestUtil')
        self.assertTrue(ob is TestUtil)

        ob = resolve_name(u'loads.tests.test_util.TestUtil')
        self.assertTrue(ob is TestUtil)

        ob = resolve_name(u'loads.tests.test_util:TestUtil')
        self.assertTrue(ob is TestUtil)

    def test_set_logger(self):
        before = len(logger.handlers)
        set_logger()
        self.assertTrue(len(logger.handlers), before + 1)

    def test_ipc_files(self):
        fd, path = mkstemp()
        os.close(fd)
        self.assertTrue(os.path.exists(path))
        register_ipc_file('ipc://' + path)
        _cleanup_ipc_files()
        self.assertFalse(os.path.exists(path))

    def test_send(self):
        sock = _BadSocket(zmq.EAGAIN)
        self.assertRaises(TimeoutError, send, sock, 'blabla')

        sock = _BadSocket(-1)
        self.assertRaises(zmq.ZMQError, send, sock, 'blabla')

    def test_recv(self):
        sock = _BadSocket(zmq.EAGAIN)
        self.assertRaises(TimeoutError, recv, sock)

        sock = _BadSocket(-1)
        self.assertRaises(zmq.ZMQError, recv, sock)

    def test_decode(self):
        params = decode_params('one:1|two:2')
        items = params.items()
        items.sort()
        self.assertEqual(items, [('one', '1'), ('two', '2')])

    def test_dump(self):
        dump = dump_stacks()
        num = len([l for l in dump if l.strip() == 'Greenlet'])

        def _job():
            gevent.sleep(.5)

        gevent.spawn(_job)
        gevent.spawn(_job)
        gevent.sleep(0)

        dump = dump_stacks()
        new_num = len([l for l in dump if l.strip() == 'Greenlet'])
        self.assertEqual(new_num - num, 3)

    def test_dns_resolve(self):
        old = util.gethostbyname

        def _gethost(*args):
            return '0.0.0.0'

        util.gethostbyname = _gethost

        try:
            res = dns_resolve('http://example.com')
        finally:
            util.gethostbyname = old

        self.assertEqual(res, ('http://0.0.0.0:80', 'example.com', '0.0.0.0'))

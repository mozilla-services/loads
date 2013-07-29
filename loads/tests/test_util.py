from tempfile import mkstemp
import datetime
import mock
import os
import unittest2 as unittest
import sys

import zmq
import gevent

import loads
from loads import util
from loads.util import (resolve_name, set_logger, logger, dns_resolve,
                        DateTimeJSONEncoder, try_import, split_endpoint)
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

        ob = resolve_name('loads')
        self.assertTrue(ob is loads)

        self.assertRaises(ImportError, resolve_name, 'xx.cc')
        self.assertRaises(ImportError, resolve_name, 'xx')
        self.assertRaises(ImportError, resolve_name, 'loads.xx')

    @mock.patch('sys.path', [])
    def test_resolve_adds_path(self):
        ob = resolve_name('loads.tests.test_util.TestUtil')
        self.assertTrue(ob is TestUtil)
        self.assertIn('', sys.path)
        old_len = len(sys.path)

        # And checks that it's not added twice
        ob = resolve_name('loads.tests.test_util.TestUtil')
        self.assertEquals(len(sys.path), old_len)

    def test_set_logger(self):
        before = len(logger.handlers)
        set_logger()
        self.assertTrue(len(logger.handlers), before + 1)

        fd, logfile = mkstemp()
        os.close(fd)
        set_logger(debug=True)
        set_logger(logfile=logfile)
        os.remove(logfile)

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
        self.assertTrue(new_num - num in (2, 3))

    def test_dns_resolve(self):
        old = util.gethostbyname

        def _gethost(*args):
            return '0.0.0.0'

        util.gethostbyname = _gethost

        try:
            res = dns_resolve('http://example.com')
            res2 = dns_resolve('http://example.com')   # cache
        finally:
            util.gethostbyname = old

        self.assertEqual(res, ('http://0.0.0.0:80', 'example.com', '0.0.0.0'))
        self.assertEqual(res, res2)

    def test_split_endpoint(self):
        res = split_endpoint('tcp://12.22.33.45:12334')
        self.assertEqual(res['scheme'], 'tcp')
        self.assertEqual(res['ip'], '12.22.33.45')
        self.assertEqual(res['port'], 12334)

        res = split_endpoint('ipc:///here/it/is')
        self.assertEqual(res['scheme'], 'ipc')
        self.assertEqual(res['path'], '/here/it/is')

        self.assertRaises(NotImplementedError, split_endpoint,
                          'wat://ddf:ff:f')

    def test_datetime_json_encoder(self):
        encoder = DateTimeJSONEncoder()
        date = datetime.datetime(2013, 5, 30, 18, 35, 11, 550482)
        delta = datetime.timedelta(0, 12, 126509)
        self.assertEquals(encoder.encode(date), '"2013-05-30T18:35:11.550482"')
        self.assertEquals(encoder.encode(delta), '12.126509')
        self.assertRaises(TypeError, encoder.encode, gevent.socket)

    def test_try_import(self):
        try_import("loads")
        try_import("loads.case", "loads.tests")
        with self.assertRaises(ImportError):
            try_import("loads.nonexistent1", "loads.nonexistent2")

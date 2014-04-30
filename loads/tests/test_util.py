from tempfile import mkstemp, mkdtemp
import datetime
import mock
import os
import unittest2 as unittest2
import sys
import StringIO
import shutil

import zmq
import gevent

import loads
from loads.tests.support import hush
from loads import util
from loads.util import (resolve_name, set_logger, logger, dns_resolve,
                        DateTimeJSONEncoder, try_import, split_endpoint,
                        null_streams, get_quantiles, pack_include_files,
                        unpack_include_files, dict_hash)
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


class FakeStdout(object):
    def fileno(self):
        return 1

    def flush(self):
        pass

    def write(self, data):
        pass


class TestUtil(unittest2.TestCase):
    def setUp(self):
        util._DNS_CACHE = {}
        self.stdout = sys.stdout
        sys.stdout = FakeStdout()

    def tearDown(self):
        sys.stdout = self.stdout

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
        self.assertTrue('' in sys.path)
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

    def test_decode_multiple_colons(self):
        params = decode_params('one:tcp://foo|two:tcp://blah')
        items = params.items()
        items.sort()
        self.assertEqual(items, [('one', 'tcp://foo'), ('two', 'tcp://blah')])

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
        with mock.patch('loads.util.gevent_socket.gethostbyname_ex') as mocked:
            mocked.return_value = ('example.com', ['example.com'],
                                   ['0.0.0.0', '1.1.1.1'])

            # Initial query should populate the cache and return
            # randomly-selected resolved address.
            url, original, resolved = dns_resolve('http://example.com')
            self.assertEqual(original, 'example.com')
            self.assertEqual(url, 'http://' + resolved + ':80')
            self.assertTrue(resolved in ("0.0.0.0", "1.1.1.1"))
            self.assertEqual(mocked.call_count, 1)
            # Subsequent queries should be fulfilled from the cache
            # and should balance between all resolved addresses.
            addrs = set()
            for _ in xrange(10):
                addrs.add(dns_resolve('http://example.com')[2])
            self.assertEqual(addrs, set(('0.0.0.0', '1.1.1.1')))
            self.assertEqual(mocked.call_count, 1)

    @hush
    @mock.patch('loads.util.gevent_socket.gethostbyname_ex')
    @mock.patch('loads.util.gevent_socket.gethostbyname')
    def test_dns_resolve_fallbacks_on_gethostbyname(self, hostbyname,
                                                    hostbyname_ex):
        # Older versions of gevent don't have the gethostbyname_ex method. Be
        # sure we fallback on the right version if the method doesn't exist.
        hostbyname_ex.side_effect = AttributeError()
        hostbyname.return_value = '0.0.0.0'
        self.assertEquals(dns_resolve(
            'http://mozilla.org'),
            ('http://0.0.0.0:80', 'mozilla.org', '0.0.0.0'))
        self.assertTrue(hostbyname.called)

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

    def test_get_quantiles(self):
        data = range(100)
        quantiles = 0, 0.1, 0.5, 0.9, 1
        res = get_quantiles(data, quantiles)
        self.assertEqual(len(res), 5)

    def test_nullstreams(self):
        stream = StringIO.StringIO()
        null_streams([stream, sys.stdout])
        stream.write('ok')
        sys.stdout.write('ok')


class TestIncludeFileHandling(unittest2.TestCase):

    def setUp(self):
        self.workdir = mkdtemp()
        self.orig_cwd = os.getcwd()
        os.chdir(self.workdir)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.workdir)

    def test_include_of_single_file(self):
        with open("test1.txt", "w") as f:
            f.write("hello world")
        filedata = pack_include_files(["test1.txt"])
        os.makedirs("outdir")
        os.chdir("outdir")
        unpack_include_files(filedata)
        self.assertEquals(os.listdir("."), ["test1.txt"])

    def test_include_of_single_file_with_explicit_location(self):
        os.makedirs("indir")
        os.makedirs("outdir")
        with open("indir/test1.txt", "w") as f:
            f.write("hello world")
        filedata = pack_include_files(["*.txt"], "./indir")
        unpack_include_files(filedata, "./outdir")
        self.assertEquals(os.listdir("outdir"), ["test1.txt"])

    def test_preservation_of_file_mode(self):
        with open("test1.sh", "w") as f:
            f.write("#!/bin/sh\necho 'hello world'\n")
        os.chmod("test1.sh", 0755)
        with open("private.txt", "w") as f:
            f.write("TOP SECRET DATA\n")
        os.chmod("private.txt", 0600)
        filedata = pack_include_files(["*.*"])
        os.unlink("test1.sh")
        os.unlink("private.txt")
        unpack_include_files(filedata)
        self.assertEquals(os.stat("test1.sh").st_mode & 0777, 0755)
        self.assertEquals(os.stat("private.txt").st_mode & 0777, 0600)

    def test_relative_globbing_and_direcotry_includes(self):
        os.makedirs("indir")
        os.makedirs("outdir")
        os.chdir("indir")
        with open("test1.txt", "w") as f:
            f.write("hello world")
        with open("test2.txt", "w") as f:
            f.write("hello world")
        os.makedirs("subdir/subsubdir")
        os.chdir("subdir/subsubdir")
        with open("test3.txt", "w") as f:
            f.write("hello world")
        os.chdir("../../../outdir")
        filedata = pack_include_files(["../indir/*.txt", "../indir/*dir"])
        unpack_include_files(filedata)
        self.assertEquals(sorted(os.listdir(".")),
                          ["subdir", "test1.txt", "test2.txt"])
        self.assertEquals(os.listdir("./subdir"), ["subsubdir"])
        self.assertEquals(os.listdir("./subdir/subsubdir"), ["test3.txt"])

    def test_unicode_unpack(self):
        # make sure we pass string
        data = (u'PK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                '\x00\x00\x00\x00\x00\x00\x00\x00\x00')

        unpack_include_files(data.encode('base64'))

    def test_dict_hash(self):
        data1 = {1: 2, 3: 4}
        data2 = {1: 2, 3: 4}

        self.assertEqual(dict_hash(data1), dict_hash(data2))

        data1['count'] = 'b'
        self.assertNotEqual(dict_hash(data1), dict_hash(data2))

        self.assertEqual(dict_hash(data1, omit_keys=['count']),
                         dict_hash(data2))

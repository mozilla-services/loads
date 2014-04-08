# adapted from
# https://github.com/paramiko/paramiko/blob/master/demos/demo_server.py
import base64
import os
import subprocess

import paramiko
from paramiko import SFTPServer, SFTPAttributes, SFTPHandle, SFTP_OK

import gevent
from gevent.event import Event
from gevent import socket
from gevent import monkey
from gevent.queue import Queue, Empty


paramiko.util.log_to_file('ssh_server.log')

_RSA = os.path.join(os.path.dirname(__file__), 'rsa.key')


# taken from https://github.com/rspivak/sftpserver
class _SFTPHandle(SFTPHandle):
    def stat(self):
        try:
            return SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)

    def chattr(self, attr):
        # python doesn't have equivalents to fchown or fchmod, so we have to
        # use the stored filename
        try:
            SFTPServer.set_file_attr(self.filename, attr)
            return SFTP_OK
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)


class _SFTPServer(paramiko.SFTPServerInterface):
    ROOT = os.getcwd()

    def _realpath(self, path):
        return path

    def list_folder(self, path):
        path = self._realpath(path)
        try:
            out = []
            flist = os.listdir(path)
            for fname in flist:
                _stat = os.stat(os.path.join(path, fname))
                attr = SFTPAttributes.from_stat(_stat)
                attr.filename = fname
                out.append(attr)
            return out
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)

    def stat(self, path):
        path = self._realpath(path)
        try:
            return SFTPAttributes.from_stat(os.stat(path))
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)

    def lstat(self, path):
        path = self._realpath(path)
        try:
            return SFTPAttributes.from_stat(os.lstat(path))
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)

    def open(self, path, flags, attr):
        path = self._realpath(path)
        try:
            binary_flag = getattr(os, 'O_BINARY', 0)
            flags |= binary_flag
            mode = getattr(attr, 'st_mode', None)
            if mode is not None:
                fd = os.open(path, flags, mode)
            else:
                # os.open() defaults to 0777 which is
                # an odd default mode for files
                fd = os.open(path, flags, 0666)
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)
        if (flags & os.O_CREAT) and (attr is not None):
            attr._flags &= ~attr.FLAG_PERMISSIONS
            SFTPServer.set_file_attr(path, attr)
        if flags & os.O_WRONLY:
            if flags & os.O_APPEND:
                fstr = 'ab'
            else:
                fstr = 'wb'
        elif flags & os.O_RDWR:
            if flags & os.O_APPEND:
                fstr = 'a+b'
            else:
                fstr = 'r+b'
        else:
            # O_RDONLY (== 0)
            fstr = 'rb'
        try:
            f = os.fdopen(fd, fstr)
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)
        fobj = _SFTPHandle(flags)
        fobj.filename = path
        fobj.readfile = f
        fobj.writefile = f
        return fobj

    def remove(self, path):
        path = self._realpath(path)
        try:
            os.remove(path)
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rename(self, oldpath, newpath):
        oldpath = self._realpath(oldpath)
        newpath = self._realpath(newpath)
        try:
            os.rename(oldpath, newpath)
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def mkdir(self, path, attr):
        path = self._realpath(path)
        try:
            os.mkdir(path)
            if attr is not None:
                SFTPServer.set_file_attr(path, attr)
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rmdir(self, path):
        path = self._realpath(path)
        try:
            os.rmdir(path)
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def chattr(self, path, attr):
        path = self._realpath(path)
        try:
            SFTPServer.set_file_attr(path, attr)
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def symlink(self, target_path, path):
        path = self._realpath(path)
        if (len(target_path) > 0) and (target_path[0] == '/'):
            # absolute symlink
            target_path = os.path.join(self.ROOT, target_path[1:])
            if target_path[:2] == '//':
                # bug in os.path.join
                target_path = target_path[1:]
        else:
            # compute relative to path
            abspath = os.path.join(os.path.dirname(path), target_path)
            if abspath[:len(self.ROOT)] != self.ROOT:
                target_path = '<error>'
        try:
            os.symlink(target_path, path)
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def readlink(self, path):
        path = self._realpath(path)
        try:
            symlink = os.readlink(path)
        except OSError, e:
            return SFTPServer.convert_errno(e.errno)
        # if it's absolute, remove the root
        if os.path.isabs(symlink):
            if symlink[:len(self.ROOT)] == self.ROOT:
                symlink = symlink[len(self.ROOT):]
                if (len(symlink) == 0) or (symlink[0] != '/'):
                    symlink = '/' + symlink
            else:
                symlink = '<error>'
        return symlink


class SSHServer(paramiko.ServerInterface):

    def __init__(self, key=_RSA, port=2200):
        self.key = paramiko.RSAKey(filename=key)
        self.data = base64.encodestring(str(self.key))
        self.shell = Event()
        self.pub_key = paramiko.RSAKey(data=base64.decodestring(self.data))
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', self.port))
        self.sock.listen(100)
        self.cmds = Queue()

    def check_channel_exec_request(self, channel, command):
        self.cmds.put((channel, command))
        return True

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        print '%r not allowed' % kind
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_publickey(self, username, key):
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return 'none'

    def check_channel_shell_request(self, channel):
        self.shell.set()
        return True

    def check_channel_pty_request(self, *args):
        return True

    def run(self):
        while True:
            client, addr = self.sock.accept()
            gevent.spawn(self.handle_connection, client, addr)

    def handle_connection(self, client, addr):
        t = paramiko.Transport(client)
        try:
            t.load_server_moduli()
        except Exception:
            print '(Failed to load moduli -- gex will be unsupported.)'
            pass

        t.add_server_key(self.key)
        t.set_subsystem_handler("sftp", paramiko.SFTPServer, _SFTPServer)

        try:
            t.start_server(server=self)
        except paramiko.SSHException:
            print '*** SSH negotiation failed.'
            t.close()
            return

        channel = t.accept()

        while t.is_active():
            try:
                chan, cmd = self.cmds.get(block=False)
            except Empty:
                pass
            else:
                print cmd
                try:
                    if hasattr(subprocess, 'check_output'):
                        result = subprocess.check_output(cmd, shell=True)
                    else:
                        result = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                                  shell=True)
                        result = result.communicate()[0]

                    chan.send(result.replace('\n', '\r\n'))
                    chan.send_exit_status(0)
                except subprocess.CalledProcessError, e:
                    if e.output:
                        output = e.output
                    else:
                        output = '%r failed' % cmd
                    chan.send_stderr(output)
                    chan.send_exit_status(e.returncode)

                chan.close()

            gevent.sleep(0)

        channel.close()
        t.close()

        return

        # interactive shell. not needed for now XXX
        # wait for auth
        chan = t.accept(20)
        if chan is None:
            print '*** No channel.'
            t.close()
            return

        self.shell.wait(10)
        if not self.shell.isSet():
            print '*** Client never asked for a shell.'
            t.close()
            return

        print 'yeah shell!'
        chan.send('\r\n\r\nTesting SSH Server\r\n\r\n')
        chan.send('Username: ')
        f = chan.makefile('rU')
        username = f.readline().strip('\r\n')
        print 'user is %r' % username

        chan.send('\r\nWelcome to a Fake world!\r\n')
        chan.send('ssh:~ $ ')

        buffer = []

        while True:
            d = chan.recv(1)
            if d == '':
                code = 0
            else:
                code = ord(d)

            if code == 3:
                break
            elif code == 13:
                chan.send('\r\n')
                cmd = ''.join(buffer)
                if cmd == 'exit':
                    chan.send('Bye !\r\n')
                    break
                try:
                    result = subprocess.check_output(cmd, shell=True)
                    chan.send(result.replace('\n', '\r\n'))
                except subprocess.CalledProcessError:
                    chan.send('That call failed.\r\n')
                chan.send('ssh:~ $ ')
                buffer = []
            else:
                buffer.append(d)
                chan.send(d)

        chan.close()
        t.close()

    def close(self):
        self.sock.close()


def main():
    monkey.patch_all()
    server = SSHServer()
    print 'Listening on port %d' % server.port
    try:
        server.run()
    finally:
        server.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass

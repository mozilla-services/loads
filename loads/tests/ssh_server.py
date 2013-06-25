# adapted from
# https://github.com/paramiko/paramiko/blob/master/demos/demo_server.py
import base64
from binascii import hexlify
import os
import sys
import traceback
import subprocess

import paramiko

import gevent
from gevent.event import Event
from gevent import socket
from gevent import monkey


paramiko.util.log_to_file('ssh_server.log')

_RSA = os.path.join(os.path.dirname(__file__), 'rsa.key')


class SSHServer(paramiko.ServerInterface):

    def __init__(self, key='rsa.key', port=2200):
        self.key = paramiko.RSAKey(filename=_RSA)
        self.data = base64.encodestring(str(self.key))
        self.event = Event()
        self.pub_key = paramiko.RSAKey(data=base64.decodestring(self.data))
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', self.port))
        self.sock.listen(100)

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_publickey(self, username, key):
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return 'password,publickey'

    def check_channel_shell_request(self, channel):
        self.event.set()
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

        try:
            t.start_server(server=self)
        except paramiko.SSHException, x:
            print '*** SSH negotiation failed.'
            t.close()
            return

        # wait for auth
        chan = t.accept(20)
        if chan is None:
            print '*** No channel.'
            t.close()
            return

        self.event.wait(10)
        if not server.event.isSet():
            print '*** Client never asked for a shell.'
            t.close()
            return

        chan.send('\r\n\r\nTesting SSH Server\r\n\r\n')
        chan.send('Username: ')
        f = chan.makefile('rU')
        username = f.readline().strip('\r\n')

        chan.send('\r\nWelcome to a Fake world!\r\n')
        chan.send('ssh:~ $ ')

        buffer = []

        while True:
            d = chan.recv(1)
            if ord(d) == 3:
                break
            elif ord(d) == 13:
                chan.send('\r\n')
                cmd = ''.join(buffer)
                if cmd == 'exit':
                    chan.send('Bye !\r\n')
                    break
                try:
                    result = subprocess.check_output(cmd, shell=True)
                    chan.send(result.replace('\n', '\r\n'))
                except subprocess.CalledProcessError, e:
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


if __name__ == '__main__':
    monkey.patch_all()
    server = SSHServer()
    print 'Listening on port %d' % server.port
    try:
        server.run()
    except KeyboardInterrupt:
        server.close()

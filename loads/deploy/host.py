import os
import tarfile
import tempfile

import paramiko


class ExecuteError(Exception):
    pass


def _prefix(prefix, msg):
    prefixed = []   # XXX stream?
    for msg in [line for line in msg.split('\n') if line != '']:
        prefixed.append('%s:%s' % (prefix, msg))
    return '\n'.join(prefixed)


class Host(object):

    def __init__(self, host, port, user, password=None, root='/tmp', key=None):
        self.password = password
        self.host = host
        self.user = user
        self.port = port
        if key is not None:
            key = os.path.expanduser(key)

        # setting up the client
        cl = paramiko.SSHClient()
        cl.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if password is not None:
            cl.connect(self.host, self.port, self.user, self.password)
        elif key is not None:
            cl.connect(self.host, self.port, username=self.user,
                       key_filename=key)
        else:
            cl.load_system_host_keys()
            cl.connect(self.host, self.port, self.user)

        self.client = cl
        sftp = paramiko.SFTPClient.from_transport(self.client.get_transport())
        self.sftp = sftp
        self.root = root
        self.curdir = None
        if self.root is not '/tmp':
            self.execute('mkdir -p %s' % self.root)
        self.curdir = root

    def chdir(self, dir):
        self.curdir = os.path.join(self.root, dir)

    def put(self, local_file, target):
        self.sftp.put(local_file, target)

    def put_dir(self, local_dir, target):
        # first, create a tarball...
        fd, tarball = tempfile.mkstemp()
        os.close(fd)
        tar = tarfile.open(tarball, "w")

        for root, dirs, files in os.walk(local_dir):
            for file_ in files:
                path = os.path.join(root, file_)
                tar.add(path, arcname=file_)

        tar.close()

        # create a directory for the tarball content
        self.execute('mkdir %s' % target)

        # next, push it to the server
        self.sftp.put(tarball, os.path.join(target, 'tarball'))

        # untar the tarball in there
        self.execute('cd %s; tar -xzvf tarball' % target, ignore_error=True)

        # remove the distant tarball
        self.execute('cd %s; rm tarball' % target)

    def execute(self, cmd, prefixed=True, ignore_error=False):
        if self.curdir is not None:
            cmd = 'cd %s;' % self.curdir + cmd
        stdin, stdout, stderr = self.client.exec_command(cmd)
        stderr = stderr.read()
        if stderr != '' and not ignore_error:
            raise ExecuteError(stderr)
        if prefixed:
            return _prefix(self.host, stdout.read()), stderr
        return stdout.read(), stderr

    def close(self):
        self.client.close()
        self.sftp.close()

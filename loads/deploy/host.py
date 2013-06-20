import os
import time
import paramiko


def _prefix(prefix, msg):
    for msg in [line for line in msg.split('\n') if line != '']:
        print '%s:%s' % (prefix, msg)


class Host(object):

    def __init__(self, host, port, user, password=None, root=None, key=None):

        time.sleep(30)   # XXX
        self.password = password
        self.host = host
        self.user = user
        self.port = port
        key = os.path.expanduser(key)
        client = paramiko.SSHClient()
        sftp = paramiko.SFTPClient()

        for cl in (client. sftp):
            cl.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if password is not None:
                cl.connect(self.host, self.port, self.user, self.password)
            elif key is not None:
                cl.connect(self.host, self.port, username=self.user,
                           key_filename=key)
            else:
                cl.load_system_host_keys()
                cl.connect(self.host, self.port, self.user)

        self.client = client
        self.sftp = sftp
        self.root = root

    def put(self, local_file, target):
        self.sftp.put(local_file, target)

    def put_dir(self, local_dir, target):
        # first, create a tarball...
        #self.sftp.put(local_file, target)
        pass

    def execute(self, cmd, prefixed=True, ignore_error=False):
        if self.root is not None:
            cmd = 'mkdir -p %s; cd %s;' % (self.root, self.root) + cmd
        stdin, stdout, stderr = self.client.exec_command(cmd)
        stderr = stderr.read()
        if stderr != '' and not ignore_error:
            raise ValueError(stderr)
        if prefixed:
            return _prefix(self.host, stdout.read()), stderr
        return stdout.read(), stderr

    def close(self):
        self.client.close()

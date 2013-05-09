import paramiko


def _prefix(prefix, msg):
    for msg in [line for line in msg.split('\n') if line != '']:
        print '%s:%s' % (prefix, msg)


class Host(object):

    def __init__(self, host, port, user, password=None):
        self.password = password
        self.host = host
        self.user = user
        self.port = port
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.WarningPolicy)
        if password is not None:
            client.connect(self.host, self.port, self.user, self.password)
        else:
            client.connect(self.host, self.port, self.user)
        self.client = client

    def execute(self, cmd):
        stdin, stdout, stderr = self.client.exec_command(cmd)
        stderr = stderr.read()
        if stderr != '':
            raise ValueError(stderr)
        return _prefix(self.host, stdout.read())

    def close(self):
        self.client.close()


def deploy(master, slaves, ssh):
    """Deploy 1 broker and n agents via ssh, run them and give back the hand
    """
    user = ssh['username']

    # deploy the broker
    host = master['host']
    print 'Deploying the broker at %s' % host
    port = master.get('port', 22)
    password = master.get('password')

    broker = Host(host, port, user, password)
    try:
        # deploying the latest Loads repo - if needed
        cmd = 'cd /tmp/;'
        cmd += 'git clone https://github.com/tarekziade/loads'
        print broker.execute(cmd)

        # building the virtualenv in a dedicated tmp file
        venv = '/usr/local/bin/virtualenv'
        venv_options = '--no-site-packages .'
        cmd = 'cd /tmp/loads; %s %s' % (venv, venv_options)
        print broker.execute(cmd)

        # installing all deps
        cmd = 'cd /tmp/loads; bin/python setup.py develop'
        print broker.execute(cmd)

    finally:
        broker.close()


if __name__ == '__main__':
    ssh = {'username': 'tarek'}
    master = {'host': 'localhost'}
    slaves = [{}]
    deploy(master, slaves, ssh)

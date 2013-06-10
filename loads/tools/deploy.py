import paramiko


def _prefix(prefix, msg):
    for msg in [line for line in msg.split('\n') if line != '']:
        print '%s:%s' % (prefix, msg)


class Host(object):

    def __init__(self, host, port, user, password=None, root=None):
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
        self.root = root

    def execute(self, cmd, prefixed=True):
        if self.root is not None:
            cmd = 'mkdir -p %s; cd %s;' % (self.root, self.root) + cmd
        stdin, stdout, stderr = self.client.exec_command(cmd)
        stderr = stderr.read()
        if stderr != '':
            raise ValueError(stderr)
        if prefixed:
            return _prefix(self.host, stdout.read())
        return stdout.read()

    def close(self):
        self.client.close()



def _deploy(host, port, user, password, root, cfg, force=False,
            endpoint='tcp://127.0.0.1:5555'):

    host = Host(host, port, user, password, root)
    try:
        # if it's running let's bypass
        if not force:
            cmd = 'cd loads; bin/circusctl --endpoint %s status' % endpoint
            try:
                print host.execute(cmd)
                return
            except ValueError:
                pass

        # deploying the latest Loads repo - if needed
        check = '[ -d "loads" ] && echo 1 || echo 0'
        res = host.execute(check, prefixed=False).strip()

        if res == '0':
            cmd = 'git clone https://github.com/mozilla-services/loads'
            print host.execute(cmd)
        else:
            cmd = 'cd loads; git pull'
            print host.execute(cmd)

        # building the virtualenv in a dedicated tmp file
        venv = '/usr/local/bin/virtualenv'
        venv_options = '--no-site-packages .'
        cmd = 'cd loads; %s %s' % (venv, venv_options)
        print host.execute(cmd)

        # installing all deps
        cmd = 'cd loads; bin/python setup.py develop; bin/pip install circus'
        print host.execute(cmd)

        # stopping any running instance
        cmd = 'cd loads; bin/circusctl quit'
        try:
            print host.execute(cmd)
        except ValueError:
            pass

        # now running
        cmd = 'cd loads; bin/circusd --daemon %s' % cfg
        print host.execute(cmd)

    finally:
        host.close()


def deploy(master, slaves, ssh):
    """Deploy 1 broker and n agents via ssh, run them and give back the hand
    """
    user = ssh['username']

    # deploy the broker
    master_host = host = master['host']
    print 'Deploying the broker at %s' % host
    port = master.get('port', 22)
    password = master.get('password')

    _deploy(host, port, user, password, root='/tmp/loads-broker',
            cfg='loads.ini')

    # now deploying slaves
    for slave in slaves:
        print 'Deploying slaves at %s' % host
        host = slave['host']
        port = slave.get('port', 22)
        password = slave.get('password')
        env = {'NUMSLAVES': slave.get('num', 10),
               'MASTER': master_host}

        _deploy(host, port, user, password, root='/tmp/loads-slaves',
                cfg='slaves.ini', endpoint='tcp://127.0.0.1:5558')


if __name__ == '__main__':
    ssh = {'username': 'tarek'}
    master = {'host': 'localhost'}
    slaves = [{'host': 'localhost'}]

    deploy(master, slaves, ssh)

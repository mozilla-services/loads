import os
from loads.deploy.host import Host, ExecuteError


class LoadsHost(Host):

    def __init__(self, host, port, user, password=None, root='/tmp',
                 key=None, venv='loads-venv'):
        Host.__init__(self, host, port, user, password, root, key)
        self.venv = os.path.join(root, venv)

    def apt_update(self):
        self.execute('sudo apt-get update')

    def apt_install(self, packages):
        cmd = ('DEBIAN_FRONTEND=noninteractive sudo apt-get -y '
               '--force-yes install %s')

        for package in packages:
            self.execute(cmd % package,  ignore_error=True)

    def check_circus(self, endpoint):
        cmd = 'cd %s;' % self.venv
        cmd += 'bin/circusctl --endpoint %s status' % endpoint
        try:
            self.execute(cmd)
            return True
        except ExecuteError:
            return False

    def create_env(self):
        # deploying the latest Loads repo - if needed
        check = '[ -d "%s" ] && echo 1 || echo 0' % self.venv
        res = self.execute(check, prefixed=False)[0].strip()
        if res == '0':
            cmd = 'git clone https://github.com/mozilla-services/loads '
            cmd += self.venv
            self.execute(cmd)
        else:
            cmd = 'cd %s; git pull' % self.venv
            self.execute(cmd)

        # changing directory
        self.chdir(self.venv)

        # building the virtualenv in a dedicated tmp file
        locations = ('/usr/bin', '/usr/local/bin')

        for index, location in enumerate(locations):
            cmd = (os.path.join(location, 'virtualenv') +
                   ' --no-site-packages .')
            try:
                self.execute(cmd)
            except ExecuteError:
                if index == len(location) - 1:
                    raise

        # python setup.py develop
        cmd = 'bin/python setup.py develop'
        self.execute(cmd, ignore_error=True)

        # deploying circus
        self.pip_install('circus')

    def pip_install(self, packages):
        if self.venv != self.curdir:
            self.chdir(self.venv)

        if isinstance(packages, str):
            packages = [packages]

        for dep in packages:
            cmd = 'bin/pip install %s' % dep
            self.execute(cmd, ignore_error=True)

    def stop_circus(self):
        # stopping any running instance
        cmd = 'bin/circusctl quit'
        try:
            self.execute(cmd)
        except ExecuteError:
            pass

    def start_circus(self, cfg):
        cmd = 'bin/circusd --daemon %s' % cfg
        self.execute(cmd)


def deploy(master, ssh, python_deps=None, system_deps=None, test_dir=None,
           circus_endpoint='tcp://0.0.0.0:5554', force=False):
    """Deploy 1 broker and n agents via ssh, run them and give back the hand
    """
    user = ssh['username']
    key = ssh['key']

    # deploy the broker
    host = master['host']
    print 'Deploying the broker at %s' % host
    port = master.get('port', 22)
    password = master.get('password')
    cfg = 'aws.ini'
    root = '/tmp/loads-broker'

    if python_deps is None:
        python_deps = []

    if system_deps is None:
        system_deps = []

    host = LoadsHost(host, port, user, password, root, key=key)
    host.apt_update()

    prereqs = system_deps + ['git', 'python-virtualenv', 'python-dev',
                             'libevent-dev']
    host.apt_install(prereqs)

    try:
        # if it's running let's bypass
        if not force and host.check_circus(circus_endpoint):
            return

        # create or check the venv
        host.create_env()

        # installing all python deps
        host.pip_install(python_deps)

        # stopping any running instance
        host.stop_circus()

        # now running
        host.start_circus(cfg)
    finally:
        host.close()

import argparse
import os
import time
import sys

import paramiko

from loads import __version__
from loads.aws import AWSConnection


def _prefix(prefix, msg):
    for msg in [line for line in msg.split('\n') if line != '']:
        print '%s:%s' % (prefix, msg)


class Host(object):

    def __init__(self, host, port, user, password=None, root=None, key=None):
        self.password = password
        self.host = host
        self.user = user
        self.port = port
        key = os.path.expanduser(key)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        time.sleep(30)
        if password is not None:
            client.connect(self.host, self.port, self.user, self.password)
        elif key is not None:
            client.connect(self.host, self.port, username=self.user,
                           key_filename=key)
        else:
            client.load_system_host_keys()
            client.connect(self.host, self.port, self.user)

        self.client = client
        self.root = root

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


def _deploy(host, port, user, password, root, cfg, force=False,
            endpoint='tcp://127.0.0.1:5555', key=None,
            python_deps=None, system_deps=None):
    if python_deps is None:
        python_deps = []

    if system_deps is None:
        system_deps = []

    host = Host(host, port, user, password, root, key=key)
    host.execute('sudo apt-get update')

    prereqs = system_deps + ['git', 'python-virtualenv', 'python-dev',
                             'libevent-dev']
    cmd = ('DEBIAN_FRONTEND=noninteractive sudo apt-get -y '
           '--force-yes install %s')

    for req in prereqs:
        host.execute(cmd % req,  ignore_error=True)

    try:
        # if it's running let's bypass
        if not force:
            cmd = 'cd loads; bin/circusctl --endpoint %s status' % endpoint
            try:
                host.execute(cmd)
                return
            except ValueError:
                pass

        # deploying the latest Loads repo - if needed
        check = '[ -d "loads" ] && echo 1 || echo 0'
        res = host.execute(check, prefixed=False)[0].strip()

        if res == '0':
            cmd = 'git clone https://github.com/mozilla-services/loads'
            host.execute(cmd)
        else:
            cmd = 'cd loads; git pull'
            host.execute(cmd)

        # building the virtualenv in a dedicated tmp file
        venv = '/usr/bin/virtualenv'
        venv_options = '--no-site-packages .'
        cmd = 'cd loads; %s %s' % (venv, venv_options)
        host.execute(cmd)

        # installing all python deps
        cmd = 'cd loads; bin/python setup.py develop; bin/pip install circus'
        host.execute(cmd, ignore_error=True)
        for dep in python_deps:
            cmd = 'cd loads;bin/pip install %s' % dep
            host.execute(cmd, ignore_error=True)

        # stopping any running instance
        cmd = 'cd loads; bin/circusctl quit'
        try:
            host.execute(cmd)
        except ValueError:
            pass

        # now running
        cmd = 'cd loads; bin/circusd --daemon %s' % cfg
        host.execute(cmd)

    finally:
        host.close()


def deploy(master, slaves, ssh, python_deps=None, system_deps=None):
    """Deploy 1 broker and n agents via ssh, run them and give back the hand
    """
    user = ssh['username']
    key = ssh['key']

    # deploy the broker
    #master_host =
    host = master['host']
    print 'Deploying the broker at %s' % host
    port = master.get('port', 22)
    password = master.get('password')

    _deploy(host, port, user, password, root='/tmp/loads-broker',
            cfg='aws.ini', key=key,
            python_deps=python_deps, system_deps=system_deps)

    # now deploying slaves
    for slave in slaves:
        print 'Deploying slaves at %s' % host
        host = slave['host']
        port = slave.get('port', 22)
        password = slave.get('password')
        #env = {'NUMSLAVES': slave.get('num', 10),
        #       'MASTER': master_host}
        _deploy(host, port, user, password, root='/tmp/loads-slaves',
                cfg='slaves.ini', endpoint='tcp://127.0.0.1:5558',
                key=key)


def main():
    parser = argparse.ArgumentParser(description='Deploy loads on Amazon')

    parser.add_argument('--access-key', help='Amazon Access Key', type=str,
                        default=os.environ.get('ACCESS_KEY'))
    parser.add_argument('--secret-key', help='Amazon Secret Key', type=str,
                        default=os.environ.get('SECRET_KEY'))
    parser.add_argument('--image-id', help='Amazon Image ID', type=str,
                        default='ami-be77e08e')
    parser.add_argument('--ssh-user', help='SSH User', type=str,
                        default='ubuntu')
    parser.add_argument('--ssh-key', help='SSH key file', type=str,
                        default=None)
    parser.add_argument('--version', action='store_true', default=False,
                        help='Displays Loads version and exits.')

    # parse args
    args = parser.parse_args()

    if args.version:
        print(__version__)
        sys.exit(0)

    print aws_deploy(args.access_key, args.secret_key, args.ssh_user,
                     args.ssh_key, args.image_id)


def aws_deploy(access_key, secret_key, ssh_user, ssh_key, image_id,
               python_deps=None, system_deps=None):
    # first task: create the AWS boxes
    aws = AWSConnection(access_key, secret_key)
    nodes = aws.create_nodes(image_id, 1)
    master, master_id = nodes[0]
    ssh = {'username': ssh_user, 'key': ssh_key}
    master = {'host': master}
    slaves = []
    try:
        deploy(master, slaves, ssh, python_deps=python_deps,
               system_deps=system_deps)
    except Exception:
        aws.terminate_nodes([master_id])
        raise

    return master, master_id


def aws_shutdown(access_key, secret_key, node_id):
    aws = AWSConnection(access_key, secret_key)
    print aws.terminate_nodes([node_id])


if __name__ == '__main__':
    sys.exit(main())

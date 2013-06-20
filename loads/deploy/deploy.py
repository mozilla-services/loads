import os
from loads.deploy.host import Host


def _deploy(host, port, user, password, root, cfg, force=False,
            endpoint='tcp://127.0.0.1:5555', key=None,
            python_deps=None, system_deps=None, test_dir=None):
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

        # copying the test dir if any
        if test_dir is not None:
            _, base = os.path.basename(test_dir)
            host.put_dir(test_dir, os.path.join('loads', base))

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


def deploy(master, slaves, ssh, python_deps=None, system_deps=None,
           test_dir=None):
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
            python_deps=python_deps, system_deps=system_deps,
            test_dir=test_dir)

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

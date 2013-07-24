import os
import functools
import sys
import StringIO
import subprocess
import atexit
import time

from loads.transport.util import DEFAULT_FRONTEND
from loads.transport import get_cluster as getcl, client
from loads.util import logger

_processes = []


def start_process(cmd):
    devnull = open('/dev/null', 'w')
    process = subprocess.Popen([sys.executable, '-m', cmd],
                               stdout=devnull, stderr=devnull)
    _processes.append(process)
    return process


def stop_process(proc):
    proc.terminate()
    if proc in _processes:
        _processes.remove(proc)


def stop_processes():
    for proc in _processes:
        try:
            proc.terminate()
        except OSError:
            pass

    _processes[:] = []


atexit.register(stop_processes)


def get_runner_args(fqn, users=1, hits=1, duration=None,
                    agents=None,
                    broker=DEFAULT_FRONTEND, test_runner=None,
                    server_url='http://localhost:9000',
                    zmq_endpoint='tcp://127.0.0.1:5558', output=['null']):

    args = {'fqn': fqn,
            'users': str(users),
            'agents': agents,
            'broker': broker,
            'test_runner': test_runner,
            'server_url': server_url,
            'zmq_endpoint': zmq_endpoint,
            'output': output}

    if duration is not None:
        args['duration'] = float(duration)
    else:
        args['hits'] = str(hits)

    return args


def get_tb():
    """runs an exception and return the traceback information"""
    try:
        raise Exception
    except Exception:
        return sys.exc_info()


def hush(func):
    """Make the passed function silent."""
    @functools.wraps(func)
    def _silent(*args, **kw):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StringIO.StringIO()
        sys.stderr = StringIO.StringIO()
        try:
            return func(*args, **kw)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    return _silent


_clusters = []


def stop_clusters():
    for cl in _clusters:
        cl.stop()


_files = []


def rm_onexit(path):
    _files.append(path)


def cleanup_files():
    for _file in _files:
        if os.path.exists(_file):
            os.remove(_file)


atexit.register(stop_clusters)
atexit.register(cleanup_files)


def get_cluster(timeout=5., movf=1., ovf=1, **kw):
    logger.debug('getting cluster')
    rm_onexit('/tmp/f-tests-cluster')
    rm_onexit('/tmp/b-tests-cluster')
    rm_onexit('/tmp/h-tests-cluster')
    rm_onexit('/tmp/r-tests-cluster')

    front = 'ipc:///tmp/f-tests-cluster'
    back = 'ipc:///tmp/b-tests-cluster'
    hb = 'ipc:///tmp/h-tests-cluster'
    reg = 'ipc:///tmp/r-tests-cluster'
    cl = getcl(frontend=front, backend=back, heartbeat=hb,
               register=reg,
               numprocesses=1, background=True, debug=False,
               timeout=movf, **kw)

    cl.start()
    time.sleep(.2)  # stabilization
    _clusters.append(cl)
    logger.debug('cluster ready')
    cli = client.Pool(size=3, frontend=front, debug=True,
                      timeout=timeout,
                      timeout_max_overflow=movf,
                      timeout_overflows=ovf)
    workers = cli.list()
    while len(workers) != 1:
        time.sleep(1.)
        workers = cli.list()

    return cli, cl

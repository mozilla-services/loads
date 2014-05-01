import os
import functools
import sys
import StringIO
import subprocess
import atexit

from loads.transport.util import DEFAULT_FRONTEND
from loads.util import logger


_processes = []


def start_process(cmd, *args):
    devnull = open('/dev/null', 'w')
    args = list(args)
    process = subprocess.Popen([sys.executable, '-m', cmd] + args,
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
                    zmq_endpoint='tcp://127.0.0.1:5558', output=['null'],
                    test_dir=None, include_file=None, python_dep=None,
                    observer=None, slave=False, agent_id=None, run_id=None,
                    loads_status=None, externally_managed=False,
                    project_name='N/A', detach=False):
    if output is None:
        output = ['null']

    if observer is None:
        observer = []

    if include_file is None:
        include_file = []

    if python_dep is None:
        python_dep = []

    args = {'fqn': fqn,
            'users': str(users),
            'agents': agents,
            'broker': broker,
            'test_runner': test_runner,
            'server_url': server_url,
            'zmq_receiver': zmq_endpoint,
            'output': output,
            'observer': observer,
            'test_dir': test_dir,
            'include_file': include_file,
            'python_dep': python_dep,
            'slave': slave,
            'externally_managed': externally_managed,
            'project_name': project_name,
            'detach': detach}

    if duration is not None:
        args['duration'] = float(duration)
    else:
        args['hits'] = str(hits)

    if agent_id is not None:
        args['agent_id'] = agent_id

    if run_id is not None:
        args['run_id'] = run_id

    if loads_status is not None:
        args['loads_status'] = loads_status

    return args


def get_tb():
    """runs an exception and return the traceback information"""
    try:
        raise Exception('Error message')
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
        debug = []

        def _debug(msg):
            debug.append(str(msg))

        old_debug = logger.debug
        logger.debug = _debug
        try:
            return func(*args, **kw)
        except:
            sys.stdout.seek(0)
            print(sys.stdout.read())
            sys.stderr.seek(0)
            print(sys.stderr.read())
            print('\n'.join(debug))
            raise
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            logger.debug = old_debug
    return _silent


_files = []


def rm_onexit(path):
    _files.append(path)


def cleanup_files():
    for _file in _files:
        if os.path.exists(_file):
            os.remove(_file)


atexit.register(cleanup_files)


# taken from http://emptysqua.re/blog/undoing-gevents-monkey-patching/
def patch_socket(aggressive=True):
    """Like gevent.monkey.patch_socket(), but stores old socket attributes for
    unpatching.
    """
    from gevent import socket
    _socket = __import__('socket')

    old_attrs = {}
    for attr in (
        'socket', 'SocketType', 'create_connection', 'socketpair', 'fromfd'
    ):
        if hasattr(_socket, attr):
            old_attrs[attr] = getattr(_socket, attr)
            setattr(_socket, attr, getattr(socket, attr))

    try:
        from gevent.socket import ssl, sslerror
        old_attrs['ssl'] = _socket.ssl
        _socket.ssl = ssl
        old_attrs['sslerror'] = _socket.sslerror
        _socket.sslerror = sslerror
    except ImportError:
        if aggressive:
            try:
                del _socket.ssl
            except AttributeError:
                pass

    return old_attrs


def unpatch_socket(old_attrs):
    """Take output of patch_socket() and undo patching."""
    _socket = __import__('socket')

    for attr in old_attrs:
        if hasattr(_socket, attr):
            setattr(_socket, attr, old_attrs[attr])

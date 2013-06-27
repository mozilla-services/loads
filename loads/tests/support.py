import functools
import sys
import StringIO
import subprocess
import atexit

from loads.transport.util import DEFAULT_FRONTEND


_processes = []


def start_process(cmd):
    devnull = open('/dev/null', 'w')
    process = subprocess.Popen([sys.executable, '-m', cmd],
                               stdout=devnull, stderr=devnull)
    _processes.append(process)


def stop_processes():
    for proc in _processes:
        try:
            proc.terminate()
        except OSError:
            pass

    _processes[:] = []


atexit.register(stop_processes)


def get_runner_args(fqn, users=1, cycles=1, duration=None,
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
        args['cycles'] = str(cycles)

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

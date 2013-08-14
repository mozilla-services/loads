import sys
import gc
import traceback
import threading
import atexit
import time
import os

import zmq.green as zmq

from loads.transport.exc import TimeoutError
from loads.util import logger

DEFAULT_FRONTEND = "ipc:///tmp/loads-front.ipc"
DEFAULT_BACKEND = "ipc:///tmp/loads-back.ipc"
DEFAULT_HEARTBEAT = "ipc:///tmp/loads-beat.ipc"
DEFAULT_REG = "ipc:///tmp/loads-reg.ipc"
DEFAULT_PUBLISHER = "ipc:///tmp/loads-publisher.ipc"
DEFAULT_BROKER_RECEIVER = "ipc:///tmp/loads-broker-receiver.ipc"

DEFAULT_TIMEOUT = 5.
DEFAULT_TIMEOUT_MOVF = 7.5
DEFAULT_TIMEOUT_OVF = 1
DEFAULT_MAX_AGE = -1
DEFAULT_MAX_AGE_DELTA = 0
_IPC_FILES = []
PARAMS = {}


@atexit.register
def _cleanup_ipc_files():
    for file in _IPC_FILES:
        file = file.split('ipc://')[-1]
        if os.path.exists(file):
            os.remove(file)


def register_ipc_file(file):
    _IPC_FILES.append(file)


def send(socket, msg, max_retries=3, retry_sleep=0.1):
    retries = 0
    while retries < max_retries:
        try:
            socket.send(msg, zmq.NOBLOCK)
            return

        except zmq.ZMQError, e:
            logger.debug('Failed on send()')
            logger.debug(str(e))
            if e.errno in (zmq.EFSM, zmq.EAGAIN):
                retries += 1
                time.sleep(retry_sleep)
            else:
                raise

    logger.debug('Sending failed')
    logger.debug(msg)
    raise TimeoutError()


def recv(socket, max_retries=3, retry_sleep=0.1):
    retries = 0
    while retries < max_retries:
        try:
            return socket.recv(zmq.NOBLOCK)
        except zmq.ZMQError, e:
            logger.debug('Failed on recv()')
            logger.debug(str(e))
            if e.errno in (zmq.EFSM, zmq.EAGAIN):
                retries += 1
                time.sleep(retry_sleep)
            else:
                raise

    logger.debug('Receiving failed')
    raise TimeoutError()


if sys.platform == "win32":
    timer = time.clock
else:
    timer = time.time


def timed(debug=False):
    def _timed(func):
        def __timed(*args, **kw):
            start = timer()
            try:
                res = func(*args, **kw)
            finally:
                duration = timer() - start
                if debug:
                    logger.debug('%.4f' % duration)
            return duration, res
        return __timed
    return _timed


def decode_params(params):
    """Decode a string into a dict. This is mainly useful when passing a dict
    trough the command line.

    The params passed in "params" should be in the form of key:value, separated
    by a pipe, the output is a python dict.
    """
    output_dict = {}
    for items in params.split('|'):
        key, value = items.split(':')
        output_dict[key] = value
    return output_dict


def encode_params(intput_dict):
    """Convert the dict given in input into a string of key:value separated
    with pipes, like spam:yeah|eggs:blah
    """
    return '|'.join([':'.join(i) for i in intput_dict.items()])


def get_params():
    return PARAMS


def dump_stacks():
    dump = []

    # threads
    threads = dict([(th.ident, th.name)
                    for th in threading.enumerate()])

    for thread, frame in sys._current_frames().items():
        if thread not in threads:
            continue
        dump.append('Thread 0x%x (%s)\n' % (thread, threads[thread]))
        dump.append(''.join(traceback.format_stack(frame)))
        dump.append('\n')

    # greenlets
    try:
        from greenlet import greenlet
    except ImportError:
        return dump

    # if greenlet is present, let's dump each greenlet stack
    for ob in gc.get_objects():
        if not isinstance(ob, greenlet):
            continue
        if not ob:
            continue   # not running anymore or not started
        dump.append('Greenlet\n')
        dump.append(''.join(traceback.format_stack(ob.gr_frame)))
        dump.append('\n')

    return dump


def verify_broker(broker_endpoint=DEFAULT_FRONTEND, timeout=1.):
    """ Return True if there's a working broker bound at broker_endpoint
    """
    from loads.transport.client import Client
    client = Client(broker_endpoint)
    try:
        return client.ping(timeout=timeout, log_exceptions=False)
    except TimeoutError:
        return None
    finally:
        client.close()


def kill_ghost_brokers(broker_endpoint=DEFAULT_FRONTEND, timeout=1.):
    """Kills ghost brokers.

    Return a pid, pids tuple. The first pid is the running broker
    and the second is a list of pids that where killed.
    """
    # checking if there's a working broker
    working_broker = verify_broker(broker_endpoint, timeout)
    if working_broker is not None:
        working_broker = int(working_broker)

    # listing running brokers and killing the ghost ones
    killed = []
    import psutil
    for pid in psutil.get_pid_list():
        if pid in (os.getpid(), os.getppid()):
            continue

        p = psutil.Process(pid)
        try:
            cmd = ' '.join(p.cmdline)
        except psutil.error.AccessDenied:
            continue

        cmd = cmd.replace('-', '.')

        if 'loads.broker' not in cmd or pid == working_broker:
            continue

        killed.append(pid)
        p.terminate()

    return working_broker, killed

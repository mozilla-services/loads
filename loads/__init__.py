import os
import sys
import argparse
import time

from loads.util import (DEFAULT_BACKEND, DEFAULT_HEARTBEAT,  # NOQA
                            DEFAULT_FRONTEND, encode_params, get_params,
                            DEFAULT_REG)
from loads.client import DEFAULT_TIMEOUT_MOVF
from loads.worker import DEFAULT_MAX_AGE, DEFAULT_MAX_AGE_DELTA
from loads.measure import Session


__all__ = ('get_cluster', 'get_params')




def get_cluster(target, numprocesses=5, frontend=DEFAULT_FRONTEND,
                backend=DEFAULT_BACKEND, heartbeat=DEFAULT_HEARTBEAT,
                register=DEFAULT_REG,
                working_dir='.', logfile='stdout',
                debug=False, background=False, worker_params=None,
                timeout=DEFAULT_TIMEOUT_MOVF, max_age=DEFAULT_MAX_AGE,
                max_age_delta=DEFAULT_MAX_AGE_DELTA):
    """Runs a Powerhose cluster.

    Options:

    - **callable**: The Python callable that will be called when the broker
      receive a job.
    - **numprocesses**: The number of workers. Defaults to 5.
    - **frontend**: the ZMQ socket to receive jobs.
    - **backend**: the ZMQ socket to communicate with workers.
    - **register** : the ZMQ socket to register workers
    - **heartbeat**: the ZMQ socket to receive heartbeat requests
    - **working_dir**: The working directory. Defaults to *"."*
    - **logfile**: The file to log into. Defaults to stdout.
    - **debug**: If True, the logs are at the DEBUG level. Defaults to False
    - **background**: If True, the cluster is run in the background.
      Defaults to False.
    - **worker_params**: a dict of params to pass to the worker. Default is
      None
    - **timeout** the maximum time allowed before the thread stacks is dumped
      and the job result not sent back.
    - **max_age**: maximum age for a worker in seconds. After that delay,
      the worker will simply quit. When set to -1, never quits.
      Defaults to -1.
    - **max_age_delta**: maximum value in seconds added to max age.
      The Worker will quit after *max_age + random(0, max_age_delta)*
      This is done to avoid having all workers quit at the same instant.
    """
    from circus import get_arbiter

    python = sys.executable
    if debug:
        debug = ' --debug'
    else:
        debug = ''
    if worker_params:
        params = encode_params(worker_params)

    broker_cmd = [python, '-m', 'loads.broker', '--logfile',  logfile,
                  debug, '--frontend', frontend, '--backend', backend,
                  '--heartbeat', heartbeat]

    worker_cmd = [python, '-m', 'loads.worker', target, '--logfile',
                  logfile, debug, '--backend', backend, '--heartbeat',
                  heartbeat, '--timeout', str(timeout), '--max-age',
                  str(max_age), '--max-age-delta', str(max_age_delta)]

    if worker_params:
        worker_cmd += ['--params', params]

    if logfile == 'stdout':
        stream = {'class': 'StdoutStream'}
    else:
        stream = {'class': 'FileStream',
                  'filename': logfile}

    watchers = [{'name': 'broker',
                 'cmd': ' '.join(broker_cmd),
                 'working_dir': working_dir,
                 'executable': python,
                 'stderr_stream': stream,
                 'stdout_stream': stream
                 },
                {'name': 'workers',
                 'cmd': ' '.join(worker_cmd),
                 'numprocesses': numprocesses,
                 'working_dir': working_dir,
                 'executable': python,
                 'stderr_stream': stream,
                 'stdout_stream': stream
                 }
                ]

    # XXX add more options
    arbiter = get_arbiter(watchers, background=background)

    # give a chance to all processes to start
    # XXX this should be in Circus
    if background:
        start = time.clock()
        while time.clock() - start < 5:
            statuses = [status == 'active' for status in
                        arbiter.statuses().values()]
            if all(statuses):
                break

    return arbiter


def main(args=sys.argv):
    from loads.util import set_logger, resolve_name

    parser = argparse.ArgumentParser(description='Run a Powerhose cluster.')

    parser.add_argument('--frontend', dest='frontend',
                        default=DEFAULT_FRONTEND,
                        help="ZMQ socket to receive jobs.")

    parser.add_argument('--backend', dest='backend',
                        default=DEFAULT_BACKEND,
                        help="ZMQ socket for workers.")

    parser.add_argument('--heartbeat', dest='heartbeat',
                        default=DEFAULT_HEARTBEAT,
                        help="ZMQ socket for the heartbeat.")

    parser.add_argument('target', help="Fully qualified name of the callable.")

    parser.add_argument('--debug', action='store_true', default=False,
                        help="Debug mode")

    parser.add_argument('--numprocesses', dest='numprocesses', default=5,
                        help="Number of processes to run.")

    parser.add_argument('--logfile', dest='logfile', default='stdout',
                        help="File to log in to .")

    args = parser.parse_args()

    set_logger(args.debug, 'loads', args.logfile)
    #set_logger(args.debug, 'circus', args.logfile)
    sys.path.insert(0, os.getcwd())  # XXX
    resolve_name(args.target)  # check the callable

    cluster = get_cluster(args.target, args.numprocesses,
                          frontend=args.frontend, backend=args.backend,
                          heartbeat=args.heartbeat, logfile=args.logfile,
                          debug=args.debug)
    try:
        cluster.start()
    except KeyboardInterrupt:
        pass
    finally:
        cluster.stop()


if __name__ == '__main__':
    main()

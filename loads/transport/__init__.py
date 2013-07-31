import sys
import time

from loads.transport.util import (DEFAULT_BACKEND, DEFAULT_HEARTBEAT,  # NOQA
                            DEFAULT_FRONTEND, encode_params, get_params,
                            DEFAULT_REG, DEFAULT_TIMEOUT_MOVF,
                            DEFAULT_MAX_AGE, DEFAULT_MAX_AGE_DELTA,
                            DEFAULT_AGENT_RECEIVER, DEFAULT_BROKER_RECEIVER)


__all__ = ('get_cluster', 'get_params')


def get_cluster(numprocesses=5, frontend=DEFAULT_FRONTEND,
                backend=DEFAULT_BACKEND, heartbeat=DEFAULT_HEARTBEAT,
                register=DEFAULT_REG, agent_receiver=DEFAULT_AGENT_RECEIVER,
                broker_receiver=DEFAULT_BROKER_RECEIVER,
                working_dir='.', logfile='stdout',
                debug=False, background=False, worker_params=None,
                timeout=DEFAULT_TIMEOUT_MOVF, max_age=DEFAULT_MAX_AGE,
                max_age_delta=DEFAULT_MAX_AGE_DELTA,
                wait=True):
    """Runs a Loads cluster.

    Options:

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

    broker_cmd = [python, '-m', 'loads.transport.broker', '--logfile',
                  logfile, debug, '--frontend', frontend, '--backend',
                  backend, '--heartbeat', heartbeat]

    worker_cmd = [python, '-m', 'loads.transport.agent',
                  '--logfile', logfile, debug,
                  '--backend', backend,
                  '--heartbeat', heartbeat,
                  '--receiver', agent_receiver,
                  '--publisher', broker_receiver,
                  '--timeout', str(timeout),
                  '--max-age', str(max_age),
                  '--max-age-delta', str(max_age_delta)]

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
    if background and wait:
        start = time.clock()
        while time.clock() - start < 5:
            statuses = [status == 'active' for status in
                        arbiter.statuses().values()]
            if all(statuses):
                break

    return arbiter

import time
import os
import subprocess
import sys

import zmq
from zmq.eventloop import ioloop, zmqstream

from loads.runners.local import LocalRunner
from loads.util import null_streams, json, logger


DEFAULT_EXTERNAL_RUNNER_RECEIVER = "ipc:///tmp/loads-external-receiver.ipc"


class ExternalRunner(LocalRunner):
    """Test runner which uses a subprocess to do the actual job.

    When ran locally, this runner makes the spawned processes report to this
    instance, otherwise it makes them report to the broker if the run is
    using a cluster.

    This runner watches the state of the underlying processes to determine if
    the runs are finished or not. Once all the runs are done, it exits.
    """

    name = 'external'
    options = {
        'process-timeout':
        ('Time to wait until we consider the run is over', int, 2, True),
    }

    def __init__(self, args=None, loop=None):
        if args is None:
            args = {}

        super(ExternalRunner, self).__init__(args)

        self._current_step = 0
        self._step_started_at = None

        self._duration = self.args.get('duration')
        self._timeout = args.get('external_process_timeout', 2)

        self._processes = []
        self._processes_pending_cleanup = []

        # hits and users are lists that can be None.
        hits, users = [1], [1]
        if self.args.get('hits') is not None:
            hits = self.args['hits']

        if self.args.get('users') is not None:
            users = self.args['users']

        self.args['hits'] = hits
        self.args['users'] = users
        self._nb_steps = max(len(hits), len(users))

        self._loop = loop or ioloop.IOLoop()

        # Check the status of the processes every so-often.(500ms)
        cb = ioloop.PeriodicCallback(self._check_processes, 500, self._loop)
        cb.start()

        self._receiver_socket = (self.args.get('zmq_receiver')
                                 or DEFAULT_EXTERNAL_RUNNER_RECEIVER)

    @property
    def step_hits(self):
        """How many hits to perform in the current step."""
        # Take the last value or fallback on the last one.
        if len(self.args['hits']) >= self._current_step + 1:
            step = self._current_step
        else:
            step = -1
        return self.args['hits'][step]

    @property
    def step_users(self):
        """How many users to spawn for the current step."""
        # Take the last value or fallback on the last one.
        if len(self.args['users']) >= self._current_step + 1:
            step = self._current_step
        else:
            step = -1
        return self.args['users'][step]

    def _check_processes(self):
        """When all the processes are finished or the duration of the test is
        more than the wanted duration, stop the loop and exit.
        """
        # Poll procs that are pending cleanup, so we don't leave zombies.
        pending = []
        for proc in self._processes_pending_cleanup:
            if proc.poll() is None:
                pending.append(proc)
        self._processes_pending_cleanup = pending

        # Find which processes have terminated, which are still active.
        active = []
        terminated = []
        for proc in self._processes:
            if proc.poll() is None:
                active.append(proc)
            else:
                if proc.returncode != 0:
                    logger.warning('Process terminated with code %r' %
                                   proc.returncode)
                terminated.append(proc)
        self._processes = active

        # Force step to be over if the processes have run for too long.
        if self._duration is not None:
            time_limit = self._duration + self._timeout
        else:
            time_limit = self.step_hits * self._timeout
        time_limit = self._step_started_at + time_limit

        # If we've reached the end of the step, start the next one.
        now = time.time()
        if len(self._processes) == 0 or now > time_limit:
            self._start_next_step()

        # Refresh the outputs every time we check the processes status,
        # but do it only if we're not in slave mode.
        if not self.slave:
            self.refresh()

    def _start_next_step(self):
        # Reap any outstanding procs from the previous step.
        # We will poll them for successful termination at next proc check.
        for proc in self._processes:
            if proc.poll() is None:
                proc.terminate()
                self._processes_pending_cleanup.append(proc)
        self._processes = []

        # Reinitialize some variables and start a new run, or exit.
        if self._current_step >= self._nb_steps:
            self.stop_run()
        else:
            self._step_started_at = time.time()
            for cur_user in range(self.step_users):
                self.spawn_external_runner(cur_user + 1)
            self._current_step += 1

    def _recv_result(self, msg):
        """Called each time the underlying processes send a message via ZMQ.

        This is used only if we are *not* in slave mode (in slave mode, the
        messages are sent directly to the broker).
        """
        # Actually add a callback to process the results to avoid blocking the
        # receival of messages.
        self._loop.add_callback(self._process_result, msg)

    def _process_result(self, msg):
        data = json.loads(msg[0])
        data_type = data.pop('data_type')

        # run_id is only used when in distributed mode, which isn't the
        # case here, so we get rid of it.
        data.pop('run_id')

        if hasattr(self.test_result, data_type):
            method = getattr(self.test_result, data_type)
            method(**data)

    def _execute(self):
        """Spawn all the tests needed and wait for them to finish.
        """
        # If we're not in slave mode, we need to receive the data ourself
        # and build up a TestResult object.  In slave mode the spawned procs
        # will report directly to the broker.
        if not self.slave:
            self.context = zmq.Context()
            self._receiver = self.context.socket(zmq.PULL)
            self._receiver.bind(self._receiver_socket)
            self._rcvstream = zmqstream.ZMQStream(self._receiver, self._loop)
            self._rcvstream.on_recv(self._recv_result)

        self._prepare_filesystem()

        self.test_result.startTestRun(self.args.get('agent_id'))
        self._start_next_step()

        self._loop.start()

        if not self.slave:
            self._receiver.close()
            self.context.destroy()

    def spawn_external_runner(self, cur_user):
        """Spawns an external runner with the given arguments.

        The loads options are passed via environment variables, that is:

            - LOADS_AGENT_ID for the id of the agent.
            - LOADS_ZMQ_RECEIVER for the address of the ZMQ socket to send the
              results to.
            - LOADS_RUN_ID for the id of the run (shared among workers of the
              same run).
            - LOADS_TOTAL_USERS for the total number of users in this step
            - LOADS_CURRENT_USER for the current user number
            - LOADS_TOTAL_HITS for the total number of hits in this step
            - LOADS_DURATION for the total duration of this step, if any

        We use environment variables because that's the easiest way to pass
        parameters to non-python executables.
        """
        cmd = self.args['test_runner'].format(test=self.args['fqn'])

        env = os.environ.copy()
        env['LOADS_AGENT_ID'] = str(self.args.get('agent_id'))
        env['LOADS_ZMQ_RECEIVER'] = self._receiver_socket
        env['LOADS_RUN_ID'] = self.args.get('run_id', '')
        env['LOADS_TOTAL_USERS'] = str(self.step_users)
        env['LOADS_CURRENT_USER'] = str(cur_user)
        if self._duration is None:
            env['LOADS_TOTAL_HITS'] = str(self.step_hits)
        else:
            env['LOADS_DURATION'] = str(self._duration)

        def silent_output():
            null_streams([sys.stdout, sys.stderr, sys.stdin])
            os.setsid()  # Run the subprocess in a new session.

        cmd_args = {
            'env': env,
            'preexec_fn': silent_output,
            'cwd': self.args.get('test_dir'),
        }

        process = subprocess.Popen(cmd.split(' '), **cmd_args)
        self._processes.append(process)

    def stop_run(self):
        self.test_result.stopTestRun(self.args.get('agent_id'))
        self._loop.stop()
        self.flush()

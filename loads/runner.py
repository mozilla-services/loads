import gevent

from loads.util import resolve_name
from loads.test_result import TestResult
from loads.relay import ZMQRelay
from loads.output import create_output


def _compute_arguments(args):
    """
    Read the given :param args: and builds up the total number of runs, the
    number of cycles, duration, users and agents to use.

    Returns a tuple of (total, cycles, duration, users, agents).
    """
    users = args.get('users', '1')
    if isinstance(users, str):
        users = users.split(':')
    users = [int(user) for user in users]
    cycles = args.get('cycles')
    duration = args.get('duration')
    if duration is None and cycles is None:
        cycles = '1'

    if cycles is not None:
        if not isinstance(cycles, list):
            cycles = [int(cycle) for cycle in cycles.split(':')]

    agents = args.get('agents', 1)

    # XXX duration based == no total
    total = 0
    if duration is None:
        for user in users:
            total += sum([cycle * user for cycle in cycles])
        if agents is not None:
            total *= agents

    return total, cycles, duration, users, agents


class Runner(object):
    """Local tests runner.

    Runs in parallel a number of tests and pass the results to the outputs.

    It can be run in two different modes:

    - "Classical" mode: Results are collected and passed to the outputs.
    - "Slave" mode: Results are sent to a ZMQ endpoint and no output is called.
    """
    def __init__(self, args):
        self.args = args
        self.fqn = args['fqn']
        if self.fqn is not None:
            self.test = resolve_name(self.fqn)
        else:
            self.test = None
        self.slave = 'slave' in args
        self.outputs = []
        self.stop = False

        (self.total, self.cycles,
         self.duration, self.users, self.agents) = _compute_arguments(args)

        self.args['cycles'] = self.cycles
        self.args['users'] = self.users
        self.args['agents'] = self.agents
        self.args['total'] = self.total

        # If we are in slave mode, set the test_result to a 0mq relay
        if self.slave:
            self._test_result = ZMQRelay(self.args)

        # The normal behavior is to collect the results locally.
        else:
            self._test_result = TestResult(args=self.args)

        if not self.slave:
            for output in self.args.get('output', ['stdout']):
                self.register_output(output)

    @property
    def test_result(self):
        return self._test_result

    def register_output(self, output_name):
        output = create_output(output_name, self.test_result, self.args)
        self.outputs.append(output)
        self.test_result.add_observer(output)

    def execute(self):
        self.running = True
        try:
            self._execute()
            if (not self.slave and
                    self.test_result.nb_errors + self.test_result.nb_failures):
                return 1
            return 0
        finally:
            self.running = False

    def _run(self, num, user):
        # creating the test case instance
        test = self.test.im_class(test_name=self.test.__name__,
                                  test_result=self.test_result,
                                  config=self.args)

        if self.stop:
            return

        if self.duration is None:
            for cycle in self.cycles:
                for current_cycle in range(cycle):
                    loads_status = cycle, user, current_cycle + 1, num
                    test(loads_status=loads_status)
                    gevent.sleep(0)
        else:
            def spawn_test():
                cycle = 0
                while True:
                    cycle = cycle + 1
                    loads_status = 0, user, cycle, num
                    test(loads_status=loads_status)
                    gevent.sleep(0)

            spawned_test = gevent.spawn(spawn_test)
            timer = gevent.Timeout(self.duration).start()
            try:
                spawned_test.join(timeout=timer)
            except (gevent.Timeout, KeyboardInterrupt):
                pass

    def _execute(self):
        """Spawn all the tests needed and wait for them to finish.
        """
        exception = None
        try:
            from gevent import monkey
            monkey.patch_all()

            if not hasattr(self.test, 'im_class'):
                raise ValueError(self.test)

            worker_id = self.args.get('worker_id', None)

            gevent.spawn(self._grefresh)
            self.test_result.startTestRun(worker_id)

            for user in self.users:
                if self.stop:
                    break

                group = [gevent.spawn(self._run, i, user)
                         for i in range(user)]
                gevent.joinall(group)

            gevent.sleep(0)
            self.test_result.stopTestRun(worker_id)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            exception = e
        finally:
            # be sure we flush the outputs that need it.
            # but do it only if we are in "normal" mode
            try:
                if not self.slave:
                    self.flush()
                else:
                    # in slave mode, be sure to close the zmq relay.
                    self.test_result.close()
            finally:
                if exception:
                    raise exception

    def flush(self):
        for output in self.outputs:
            if hasattr(output, 'flush'):
                output.flush()

    def refresh(self):
        for output in self.outputs:
            if hasattr(output, 'refresh'):
                output.refresh()

    def _grefresh(self):
        self.refresh()
        if not self.stop:
            gevent.spawn_later(.1, self._grefresh)

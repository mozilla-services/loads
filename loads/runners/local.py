import os
import subprocess
import sys
import shutil

import gevent

from loads.util import resolve_name, glob, logger
from loads.results import ZMQTestResult, TestResult
from loads.output import create_output


def _compute_arguments(args):
    """
    Read the given :param args: and builds up the total number of runs, the
    number of hits, duration, users and agents to use.

    Returns a tuple of (total, hits, duration, users, agents).
    """
    users = args.get('users', '1')
    if isinstance(users, str):
        users = users.split(':')
    users = [int(user) for user in users]
    hits = args.get('hits')
    duration = args.get('duration')
    if duration is None and hits is None:
        hits = '1'

    if hits is not None:
        if not isinstance(hits, list):
            hits = [int(hit) for hit in hits.split(':')]

    agents = args.get('agents', 1)

    # XXX duration based == no total
    total = 0
    if duration is None:
        for user in users:
            total += sum([hit * user for hit in hits])
        if agents is not None:
            total *= agents

    return total, hits, duration, users, agents


class LocalRunner(object):
    """Local tests runner.

    Runs the tests for the given number of users.

    This runner can be used in two different modes:

    - The "classical" mode where the results are collected and passed to the
      outputs.
    - The "slave" mode where the results are sent to a ZMQ endpoint and no
      output is called.
    """

    name = 'local'
    options = {}

    def __init__(self, args):
        self.args = args
        self.fqn = args.get('fqn')
        self.test = None
        self.slave = args.get('slave', False)
        self.run_id = None

        # Only resolve the name of the test if we're using the default python
        # test-runner.
        if args.get('test_runner') is None and self.fqn:
            self.test = resolve_name(self.fqn)
        else:
            self.test = None

        self.outputs = []
        self.stop = False

        (self.total, self.hits,
         self.duration, self.users, self.agents) = _compute_arguments(args)

        self.args['hits'] = self.hits
        self.args['users'] = self.users
        self.args['agents'] = self.agents
        self.args['total'] = self.total

        # If we are in slave mode, set the test_result to a 0mq relay
        if self.slave:
            self._test_result = ZMQTestResult(self.args)

        # The normal behavior is to collect the results locally.
        else:
            self._test_result = TestResult(args=self.args)

        if not self.slave:
            for output in self.args.get('output', ['stdout']):
                self.register_output(output)

    def _resolve_name(self):
        if self.fqn is not None:
            self.test = resolve_name(self.fqn)

    @property
    def test_result(self):
        return self._test_result

    def register_output(self, output_name):
        output = create_output(output_name, self.test_result, self.args)
        self.outputs.append(output)
        self.test_result.add_observer(output)

    def _deploy_python_deps(self, deps=None):
        # XXX pip hack to avoid uninstall
        # deploy python deps if asked
        deps = deps or self.args.get('python_dep', [])
        if deps == []:
            return

        nil = "lambda *args, **kw: None"
        code = ["from pip.req import InstallRequirement",
                "InstallRequirement.uninstall = %s" % nil,
                "InstallRequirement.commit_uninstall = %s" % nil,
                "import pip", "pip.main()"]

        cmd = [sys.executable, '-c', '"%s"' % ';'.join(code),
               'install', '-t', 'deps', '-I']

        for dep in deps:
            logger.debug('Deploying %r in %r' % (dep, os.getcwd()))
            process = subprocess.Popen(' '.join(cmd + [dep]), shell=True,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise Exception(stderr)

        sys.path.insert(0, 'deps')

    def execute(self):
        """The method to start the load runner."""
        old_location = os.getcwd()
        self.running = True
        try:
            self._execute()
            if (not self.slave and
                    self.test_result.nb_errors + self.test_result.nb_failures):
                return 1
            return 0
        finally:
            self.running = False
            os.chdir(old_location)

    def _run(self, num, user):
        """This method is actually spawned by gevent so there is more than
        one actual test suite running in parallel.
        """
        # creating the test case instance
        test = self.test.im_class(test_name=self.test.__name__,
                                  test_result=self.test_result,
                                  config=self.args)

        if self.stop:
            return

        if self.duration is None:
            for hit in self.hits:
                gevent.sleep(0)

                for current_hit in range(hit):
                    loads_status = self.args.get('loads_status',
                                                 (hit, user, current_hit + 1,
                                                  num))
                    test(loads_status=loads_status)
                    gevent.sleep(0)
        else:
            def spawn_test():
                hit = 0
                while True:
                    hit = hit + 1
                    loads_status = 0, user, hit, num
                    test(loads_status=loads_status)
                    gevent.sleep(0)

            spawned_test = gevent.spawn(spawn_test)
            timer = gevent.Timeout(self.duration).start()
            try:
                spawned_test.join(timeout=timer)
            except (gevent.Timeout, KeyboardInterrupt):
                pass

    def _prepare_filesystem(self):
        test_dir = self.args.get('test_dir')

        # in standalone mode we take care of creating
        # the files
        if test_dir is not None:
            if not self.slave:
                test_dir = test_dir + '-%d' % os.getpid()

                if not os.path.exists(test_dir):
                    os.makedirs(test_dir)

                # grab the files, if any
                includes = self.args.get('include_file', [])

                for file_ in glob(includes):
                    logger.debug('Copying %r' % file_)
                    target = os.path.join(test_dir, file_)
                    if os.path.isdir(file_):
                        if os.path.exists(target):
                            shutil.rmtree(target)
                        shutil.copytree(file_, target)
                    else:
                        shutil.copyfile(file_, target)

            # change to execution directory if asked
            logger.debug('chdir %r' % test_dir)
            os.chdir(test_dir)

    def _execute(self):
        """Spawn all the tests needed and wait for them to finish.
        """
        self._prepare_filesystem()
        self._deploy_python_deps()
        self._run_python_tests()

    def _run_python_tests(self):
        # resolve the name now
        self._resolve_name()

        agent_id = self.args.get('agent_id')
        exception = None
        try:
            if not self.args.get('no_patching', False):
                from gevent import monkey
                monkey.patch_all()

            if not hasattr(self.test, 'im_class'):
                raise ValueError("The FQN of the test doesn't point to a test "
                                 "class (%s)." % self.test)

            gevent.spawn(self._grefresh)

            if not self.args.get('externally_managed'):
                self.test_result.startTestRun(agent_id)

            for user in self.users:
                if self.stop:
                    break

                group = []
                for i in range(user):
                    group.append(gevent.spawn(self._run, i, user))
                    gevent.sleep(0)

                gevent.joinall(group)

            gevent.sleep(0)

            if not self.args.get('externally_managed'):
                self.test_result.stopTestRun(agent_id)
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
        if not self.stop:
            for output in self.outputs:
                if hasattr(output, 'refresh'):
                    output.refresh(self.run_id)

    def _grefresh(self):
        self.refresh()
        if not self.stop:
            gevent.spawn_later(.1, self._grefresh)

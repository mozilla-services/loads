import os
import subprocess
import sys

import gevent

from loads.util import (resolve_name, logger, pack_include_files,
                        unpack_include_files, set_logger)
from loads.results import ZMQTestResult, TestResult, ZMQSummarizedTestResult
from loads.output import create_output


DEFAULT_LOGFILE = os.path.join('/tmp', 'loads-worker.log')


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
        if self.slave:
            set_logger(True, logfile=args.get('logfile', DEFAULT_LOGFILE))

        self.run_id = None
        self.project_name = args.get('project_name', 'N/A')
        self._test_result = None
        self.outputs = []
        self.stop = False

        (self.total, self.hits,
         self.duration, self.users, self.agents) = _compute_arguments(args)

        self.args['hits'] = self.hits
        self.args['users'] = self.users
        self.args['agents'] = self.agents
        self.args['total'] = self.total

    def _resolve_name(self):
        if self.fqn is not None:
            self.test = resolve_name(self.fqn)

    @property
    def test_result(self):
        if self._test_result is None:
            # If we are in slave mode, set the test_result to a 0mq relay
            if self.slave:
                if self.args.get('batched', False):
                    self._test_result = ZMQSummarizedTestResult(self.args)
                else:
                    self._test_result = ZMQTestResult(self.args)

            # The normal behavior is to collect the results locally.
            else:
                self._test_result = TestResult(args=self.args)

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

        # accepting lists and list of comma-separated values
        pydeps = []
        for dep in deps:
            dep = [d.strip() for d in dep.split(',')]
            for d in dep:
                if d == '':
                    continue
                pydeps.append(d)

        build_dir = os.path.join(self.args['test_dir'],
                                 'build-', str(os.getpid()))
        nil = "lambda *args, **kw: None"
        code = ["from pip.req import InstallRequirement",
                "InstallRequirement.uninstall = %s" % nil,
                "InstallRequirement.commit_uninstall = %s" % nil,
                "import pip", "pip.main()"]

        cmd = [sys.executable, '-c', '"%s"' % ';'.join(code),
               'install', '-t', 'deps', '-I', '-b', build_dir]

        for dep in pydeps:
            logger.debug('Deploying %r in %r' % (dep, os.getcwd()))
            process = subprocess.Popen(' '.join(cmd + [dep]), shell=True,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            # XXX see https://github.com/mozilla-services/loads/issues/253
            if 'Successfully installed' not in stdout:
                logger.debug('Failed to deploy %r' % dep)
                logger.debug('Error: %s' % str(stderr))
                logger.debug('Stdout: %s' % str(stdout))
                logger.debug("Command used: %s" % str(' '.join(cmd + [dep])))
                raise Exception(stderr)
            else:
                logger.debug('Successfully deployed %r' % dep)

        sys.path.insert(0, 'deps')

    def execute(self):
        """The method to start the load runner."""
        if not self.slave:
            for output in self.args.get('output', ['stdout']):
                self.register_output(output)

        old_location = os.getcwd()
        self.running = True
        try:
            self._execute()
            if (not self.slave and
                    self.test_result.nb_errors + self.test_result.nb_failures):
                return 1
            return 0
        except Exception:
            self.test_result.addError('XXX', sys.exc_info(), (0, 0, 0, 0))
            raise
        finally:
            self.test_result.close()
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
                loads_status = list(self.args.get('loads_status',
                                                  (hit, user, 0, num)))
                for current_hit in range(hit):
                    loads_status[2] = current_hit + 1
                    test(loads_status=list(loads_status))
                    gevent.sleep(0)
        else:
            def spawn_test():
                loads_status = list(self.args.get('loads_status',
                                                  (0, user, 0, num)))
                while True:
                    loads_status[2] += 1
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

                # Copy over the include files, if any.
                # It's inefficient to package them up and then immediately
                # unpackage them, but this has the advantage of ensuring
                # consistency with how it's done in the distributed case.
                includes = self.args.get('include_file', [])
                logger.debug("unpacking %s" % str(includes))
                filedata = pack_include_files(includes)
                unpack_include_files(filedata, test_dir)

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
        logger.debug('Resolving the test fqn')
        self._resolve_name()

        logger.debug('Ready to spawn greenlets for testing.')
        agent_id = self.args.get('agent_id')
        exception = None
        try:
            if not self.args.get('no_patching', False):
                logger.debug('Gevent monkey patches the stdlib')
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
            logger.debug('Test over - cleaning up')
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
                    logger.debug('We had an exception, re-raising it')
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

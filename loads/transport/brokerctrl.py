import functools
import random
import time
import sys
import traceback
from collections import defaultdict
import datetime
from uuid import uuid4

from loads.db import get_database
from loads.transport.util import DEFAULT_AGENT_TIMEOUT
from loads.util import logger, resolve_name, json, unbatch
from loads.results import RemoteTestResult


class NotEnoughWorkersError(Exception):
    pass


class NoDetailedDataError(Exception):
    pass


def _compute_observers(observers):
    """Reads the arguments and returns an observers list"""
    def _resolver(name):
        try:
            return resolve_name('loads.observers.%s' % name)
        except ImportError:
            return resolve_name(name)

    if observers is None:
        return []

    return [_resolver(observer) for observer in observers]


class BrokerController(object):
    def __init__(self, broker, loop, db='python', dboptions=None,
                 agent_timeout=DEFAULT_AGENT_TIMEOUT):
        self.broker = broker
        self.loop = loop

        # agents registration and timers
        self._agents = {}
        self._agent_times = {}
        self.agent_timeout = agent_timeout
        self._runs = {}

        # local DB
        if dboptions is None:
            dboptions = {}
        self._db = get_database(db, self.loop, **dboptions)

        # cached agents results
        def default_status():
            return {"result": {"status": {},
                               "command": "STATUS"}}
        self._cached_status = defaultdict(default_status)

    @property
    def agents(self):
        return self._agents

    def _remove_agent(self, agent_id, reason='unspecified'):
        logger.debug('%r removed. %s' % (agent_id, reason))

        if agent_id in self._agents:
            del self._agents[agent_id]

        if agent_id in self._agent_times:
            del self._agent_times[agent_id]

        if agent_id in self._runs:
            del self._runs[agent_id]

        if agent_id in self._cached_status:
            del self._cached_status[agent_id]

    def register_agent(self, agent_info):
        agent_id = agent_info['agent_id']

        if agent_id not in self._agents:
            logger.debug('registring agent %s' % str(agent_info))
            self._agents[agent_id] = agent_info

    def unregister_agents(self, reason='unspecified', keep_fresh=True):
        logger.debug('unregistring some agents')
        for agent_id in self._agents.keys():
            self.unregister_agent(agent_id, reason)

    def unregister_agent(self, agent_id, reason='unspecified'):
        if agent_id in self._agents:
            self._remove_agent(agent_id, reason)

    def _associate(self, run_id, agents):
        when = time.time()

        for agent_id in agents:
            self._runs[agent_id] = run_id, when

    def reserve_agents(self, num, run_id):
        # we want to run the same command on several agents
        # provisionning them
        agents = []
        available = [wid for wid in self._agents.keys()
                     if wid not in self._runs]

        if num > len(available):
            raise NotEnoughWorkersError('Not Enough agents')

        while len(agents) < num:
            agent_id = random.choice(available)
            if self._check_agent(agent_id):
                agents.append(agent_id)
                available.remove(agent_id)

        self._associate(run_id, agents)
        return agents

    def send_to_agent(self, agent_id, msg, target=None):
        # now we can send to the right guy
        data = [str(agent_id), '', self.broker.pid, '']
        if target is not None:
            data += [target, '']

        data.append(msg)
        try:
            self.broker._backend.send_multipart(data)
        except Exception, e:
            logger.debug('Failed to send %s' % str(msg))
            # we don't want to die on error. we just log it
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc = traceback.format_tb(exc_traceback)
            exc.insert(0, str(e))
            logger.error('\n'.join(exc))
            logger.debug('Removing agent')
            self._remove_agent(agent_id, '\n'.join(exc))

    def clean(self):
        """This is called periodically to :

        - send a _STATUS command to all active agents to refresh their status
        - detect agents that have not responded for a while and discard them
          from the run and from the agents list
        """
        now = time.time()

        for agent_id, (run_id, when) in self._runs.items():
            # when was the last time we've got a response ?
            last_contact = self._agent_times.get(agent_id)

            # is the agent not responding since a while ?
            if (last_contact is not None and
               now - last_contact > self.agent_timeout):
                # let's kill the agent...
                lag = now - last_contact
                logger.debug('No response from agent since %d s.' % lag)
                logger.debug('Killing agent %s' % str(agent_id))
                quit = json.dumps({'command': 'QUIT'})
                self.send_to_agent(agent_id, quit)

                # and remove it from the run
                run_id = self._terminate_run(agent_id)

                if run_id is not None:
                    logger.debug('publishing end of run')
                    # if the tests are finished, publish this on the pubsub.
                    msg = json.dumps({'data_type': 'run-finished',
                                      'run_id': run_id})
                    self.broker._publisher.send(msg)
            else:
                # initialize the timer
                if last_contact is None:
                    self._agent_times[agent_id] = now

                # sending a _STATUS call to on each active agent
                status_msg = json.dumps({'command': '_STATUS',
                                         'run_id': run_id})
                self.send_to_agent(agent_id, status_msg)

    def update_status(self, agent_id, result):
        """Checks the status of the processes. If all the processes are done,
           call self.test_ended() and return the run_id. Returns None
           otherwise.
        """
        if result.get('command') == '_STATUS':
            self._cached_status[agent_id] = {'result': result}

        def _extract_status(st):
            if isinstance(st, basestring):
                return st
            return st['status']

        statuses = [_extract_status(st)
                    for st in result['status'].values()]

        if 'running' not in statuses:
            logger.debug('agent %s not running anything' % agent_id)
            return self._terminate_run(agent_id)

        self._agent_times[agent_id] = time.time()

    def _terminate_run(self, agent_id):
        # ended
        if agent_id in self._agent_times:
            del self._agent_times[agent_id]

        if agent_id not in self._runs:
            return

        run_id, when = self._runs[agent_id]
        logger.debug('removing %s from run %s' % (agent_id, run_id))

        del self._runs[agent_id]

        # is the whole run over ?
        running = [run_id_ for (run_id_, when_) in self._runs.values()]

        # we want to tell the world if the run has ended
        if run_id not in running:
            logger.debug('the whole run %s is over, removing it' % run_id)
            self.test_ended(run_id)
            return run_id

    #
    # DB APIs
    #
    def save_metadata(self, run_id, data):
        self._db.save_metadata(run_id, data)

    def update_metadata(self, run_id, **metadata):
        self._db.update_metadata(run_id, **metadata)

    def get_metadata(self, msg, data):
        return self._db.get_metadata(data['run_id'])

    def save_data(self, agent_id, data):
        # registering the agent as alive
        hostname = data.get('hostname', '?')
        agent_pid = agent_id.split('-')[-1]
        self.register_agent({'pid': agent_pid, 'hostname': hostname,
                             'agent_id': agent_id})

        if agent_id in self._runs:
            data['run_id'], data['started'] = self._runs[agent_id]
        else:
            # this means we are receiving data from an agent that's
            # no longer associated with the run, so
            # we want to associate it back
            self._associate(data.get('run_id'), [agent_id])

        if data.get('data_type') == 'batch':
            for data_type, message in unbatch(data):
                message['data_type'] = data_type
                callback = functools.partial(self._db.add, message)
                self.loop.add_callback(callback)
        else:
            self._db.add(data)

    def get_urls(self, msg, data):
        run_id = data['run_id']
        return self._db.get_urls(run_id)

    def get_data(self, msg, data):
        # XXX stream ?
        run_id = data['run_id']

        if self._db.is_summarized(run_id):
            raise NoDetailedDataError(run_id)

        start = data.get('start')
        if start is not None:
            start = int(start)

        size = data.get('size')
        if size is not size:
            size = int(size)

        options = {'data_type': data.get('data_type'),
                   'groupby': data.get('groupby', False),
                   'start': start,
                   'size': size}

        return list(self._db.get_data(run_id, **options))

    def get_counts(self, msg, data):
        run_id = data['run_id']
        return self._db.get_counts(run_id)

    def flush_db(self):
        return self._db.flush()

    def _check_agent(self, agent_id):
        # XXX we'll want agents to register themselves
        # again after each heartbeat
        #
        # The broker will removing idling agents
        # just before sending a hearbeat.
        #
        # That will let us make sure a dead agent on
        # a distant box is removed
        if agent_id in self._agent_times:
            last_contact = self._agent_times.get(agent_id)
            if last_contact is not None:
                duration = time.time() - last_contact
                if duration > self.agent_timeout:
                    logger.debug('The agent %r is slow (%.2f)' % (agent_id,
                                                                  duration))
                    return False
        return True

    def run_command(self, cmd, msg, data):
        cmd = cmd.lower()
        target = msg[0]

        # command for agents
        if cmd.startswith('agent_'):
            command = cmd[len('agent_'):].upper()

            # when a STATUS call is made, we make it
            # an indirect call
            if command == 'STATUS':
                command = '_STATUS'

            data['command'] = command
            agent_id = str(data['agent_id'])
            self.send_to_agent(agent_id, json.dumps(data), target=target)

            if command == '_STATUS':
                logger.debug('current cache %s' % str(self._cached_status))
                return self._cached_status[agent_id]

            return

        if not hasattr(self, cmd):
            raise AttributeError(cmd)

        # calling the command asynchronously
        def _call():
            try:
                res = getattr(self, cmd)(msg, data)
                res = {'result': res}
                self.broker.send_json(target, res)
            except Exception, e:
                logger.debug('Failed')
                exc_type, exc_value, exc_traceback = sys.exc_info()
                exc = traceback.format_tb(exc_traceback)
                exc.insert(0, str(e))
                self.broker.send_json(target, {'error': exc})

        self.loop.add_callback(_call)
        return

    def list_runs(self, msg, data):
        runs = defaultdict(list)
        for agent_id, (run_id, when) in self._runs.items():
            runs[run_id].append((agent_id, when))
        return runs

    def stop_run(self, msg, data):
        run_id = data['run_id']
        agents = []

        for agent_id, (_run_id, when) in self._runs.items():
            if run_id != _run_id:
                continue
            agents.append(agent_id)

        if len(agents) == 0:
            # we don't have any agents running that test, let's
            # force the flags in the DB
            self.update_metadata(run_id, stopped=True, active=False,
                                 ended=time.time())
            return []

        # now we have a list of agents to stop
        stop_msg = json.dumps({'command': 'STOP'})

        for agent_id in agents:
            self.send_to_agent(agent_id, stop_msg)

        return agents

    #
    # Observers
    #
    def test_ended(self, run_id):
        # first of all, we want to mark it done in the DB
        logger.debug('test %s ended marking the metadata' % run_id)
        self.update_metadata(run_id, stopped=True, active=False,
                             ended=time.time())

        # we want to ping all observers that things are done
        # for a given test.
        # get the list of observers
        args = self._db.get_metadata(run_id)
        observers = _compute_observers(args.get('observer'))

        if observers == []:
            self._db.summarize_run(run_id)
            return

        logger.debug('test %s ended calling the observers' % run_id)

        # if we are using the web dashboard - we're just providing a link
        if self.broker.web_root is not None:
            test_result = '%s/run/%s' % (self.broker.web_root, run_id)
        else:
            # rebuild the test result instance
            test_result = RemoteTestResult(args=args)
            test_result.args = args

            if 'started' in args:
                started = args['started']
                started = datetime.datetime.utcfromtimestamp(started)
                test_result.startTestRun(when=started)

            test_result.set_counts(self._db.get_counts(run_id))

        # for each observer we call it with the test results
        for observer in observers:
            options = {}
            prefix = 'observer_%s_' % observer.name
            for name, value in args.items():
                if name.startswith(prefix):
                    options[name[len(prefix):]] = value

            # get the options
            try:
                observer(args=args, **options)(test_result)
            except Exception:
                # the observer code failed. We want to log it
                logger.error('%r failed' % observer)

        self._db.summarize_run(run_id)

    #
    # The run apis
    #
    def run(self, msg, data):
        target = msg[0]

        # create a unique id for this run
        run_id = str(uuid4())

        # get some agents
        try:
            agents = self.reserve_agents(data['agents'], run_id)
        except NotEnoughWorkersError:
            self.broker.send_json(target, {'error': 'Not enough agents'})
            return

        # make sure the DB is prepared
        self._db.prepare_run()

        # send to every agent with the run_id and the receiver endpoint
        data['run_id'] = run_id
        data['args']['zmq_receiver'] = self.broker.endpoints['receiver']

        # replace CTRL_RUN by RUN
        data['command'] = 'RUN'

        # rebuild the ZMQ message to pass to agents
        msg = json.dumps(data)

        # notice when the test was started
        data['args']['started'] = time.time()
        data['args']['active'] = True

        # save the tests metadata in the db
        self.save_metadata(run_id, data['args'])
        self.flush_db()

        for agent_id in agents:
            self.send_to_agent(agent_id, msg)

        # tell the client which agents where selected.
        res = {'result': {'agents': agents, 'run_id': run_id}}
        self.broker.send_json(target, res)

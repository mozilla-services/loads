import random
import time
import sys
import traceback
from collections import defaultdict
import datetime
from uuid import uuid4

from loads.db import get_database
from loads.transport.client import DEFAULT_TIMEOUT_MOVF
from loads.util import logger, resolve_name, json
from loads.results import RemoteTestResult


class NotEnoughWorkersError(Exception):
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
                 agent_timeout=DEFAULT_TIMEOUT_MOVF):
        self.broker = broker
        self.loop = loop

        # agents registration and timers
        self._agents = []
        self._agent_times = {}
        self.agent_timeout = agent_timeout
        self._runs = {}

        # local DB
        if dboptions is None:
            dboptions = {}
        self._db = get_database(db, self.loop, **dboptions)

    @property
    def agents(self):
        return self._agents

    def _remove_agent(self, agent_id):
        logger.debug('%r removed' % agent_id)
        if agent_id in self._agents:
            self._agents.remove(agent_id)

        if agent_id in self._agent_times:
            del self._agent_times[agent_id]

        if agent_id in self._runs:
            del self._runs[agent_id]

    def register_agent(self, agent_id):
        if agent_id not in self._agents:
            self._agents.append(agent_id)

    def unregister_agents(self):
        self._agents[:] = []

    def unregister_agent(self, agent_id):
        if agent_id in self._agents:
            self._remove_agent(agent_id)

    def _associate(self, run_id, agents):
        when = time.time()

        for agent_id in agents:
            self._runs[agent_id] = run_id, when

    def reserve_agents(self, num, run_id):
        # we want to run the same command on several agents
        # provisionning them
        agents = []
        available = [wid for wid in self._agents if wid not in self._runs]

        if num > len(available):
            raise NotEnoughWorkersError('Not Enough agents')

        while len(agents) < num:
            agent_id = random.choice(available)
            if self._check_agent(agent_id):
                agents.append(agent_id)
                available.remove(agent_id)

        self._associate(run_id, agents)
        return agents

    def send_to_agent(self, agent_id, msg):
        msg = list(msg)

        # now we can send to the right guy
        msg.insert(0, agent_id)
        try:
            self.broker._backstream.send_multipart(msg)
        except Exception, e:
            logger.debug('Failed to send %s' % str(msg))
            # we don't want to die on error. we just log it
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc = traceback.format_tb(exc_traceback)
            exc.insert(0, str(e))
            logger.error('\n'.join(exc))
            logger.debug('Removing agent')
            self._remove_agent(agent_id)

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

            # is the agent not responding since 10 seconds ?
            if (last_contact is not None and
               now - last_contact > self.agent_timeout):
                # let's kill the agent...
                quit = ['', json.dumps({'command': 'QUIT'})]
                self.send_to_agent(agent_id, quit)

                # and remove it from the run
                run_id = self.update_status(agent_id, ['terminated'])

                if run_id is not None:
                    # if the tests are finished, publish this on the pubsub.
                    msg = json.dumps({'data_type': 'run-finished',
                                      'run_id': run_id})
                    self.broker._publisher.send(msg)
            else:
                # initialize the timer
                if last_contact is None:
                    self._agent_times[agent_id] = now

                # sending a _STATUS call to on each active agent
                status_msg = ['', json.dumps({'command': '_STATUS',
                                              'run_id': run_id})]
                self.send_to_agent(agent_id, status_msg)

    def update_status(self, agent_id, processes_status):
        """Checks the status of the processes. If all the processes are done,
           call self.test_ended() and return the run_id. Returns None
           otherwise.
        """
        self._agent_times[agent_id] = time.time()

        if 'running' not in processes_status:
            # ended
            if agent_id in self._agent_times:
                del self._agent_times[agent_id]

            if agent_id in self._runs:
                run_id, when = self._runs[agent_id]
                del self._runs[agent_id]

            # is the whole run over ?
            running = [run_id_ for (run_id_, when_) in self._runs.values()]

            # we want to tell the world if the run has ended
            if run_id not in running:
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
        if agent_id in self._runs:
            data['run_id'], data['started'] = self._runs[agent_id]

        self._db.add(data)

    def get_urls(self, msg, data):
        run_id = data['run_id']
        return self._db.get_urls(run_id)

    def get_data(self, msg, data):
        # XXX stream ?
        run_id = data['run_id']

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
        target = msg[:-1]

        # command for agents
        if cmd.startswith('agent_'):
            data['command'] = cmd[len('agent_'):].upper()
            msg = msg[:2] + [json.dumps(data)] + msg[2:]
            self.send_to_agent(str(data['agent_id']), msg)
            return    # returning None because it's async

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
        stop_msg = msg[:-1] + [json.dumps({'command': 'STOP'})]

        for agent_id in agents:
            self.send_to_agent(agent_id, stop_msg)

        return agents

    #
    # Observers
    #
    def test_ended(self, run_id):
        # first of all, we want to mark it done in the DB
        self.update_metadata(run_id, stopped=True, active=False,
                             ended=time.time())

        # we want to ping all observers that things are done
        # for a given test.
        # get the list of observers
        args = self._db.get_metadata(run_id)
        observers = _compute_observers(args.get('observer'))

        if observers == []:
            return

        # rebuild the test result instance
        test_result = RemoteTestResult(args=args)
        test_result.args = args

        data = list(self._db.get_data(run_id, size=1))
        if len(data) > 0:
            started = datetime.datetime.utcfromtimestamp(data[0]['started'])
            test_result.startTestRun(when=started)

        test_result.set_counts(self._db.get_counts(run_id))

        # for each observer we call it with the test results
        for observer in observers:
            try:
                observer(test_result, args)
            except Exception:
                # the observer code failed. We want to log it
                logger.error('%r failed' % observer)

    #
    # The run apis
    #
    def run(self, msg, data):
        target = msg[:-1]

        # create a unique id for this run
        run_id = str(uuid4())

        # get some agents
        try:
            agents = self.reserve_agents(data['agents'], run_id)
        except NotEnoughWorkersError:
            self.broker.send_json(target, {'error': 'Not enough agents'})
            return

        # send to every agent with the run_id and the receiver endpoint
        data['run_id'] = run_id
        data['args']['zmq_receiver'] = self.broker.endpoints['receiver']

        # replace CTRL_RUN by RUN
        data['command'] = 'RUN'

        # rebuild the ZMQ message to pass to agents
        msg[2] = json.dumps(data)

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

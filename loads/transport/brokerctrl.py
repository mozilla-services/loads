import random
import psutil
import time
import sys
import traceback
import json
from collections import defaultdict

from loads.db.brokerdb import BrokerDB, DEFAULT_DBDIR
from loads.transport.client import DEFAULT_TIMEOUT_MOVF
from loads.util import logger


class NotEnoughWorkersError(Exception):
    pass


class BrokerController(object):
    def __init__(self, broker, loop, dbdir=DEFAULT_DBDIR,
                 worker_timeout=DEFAULT_TIMEOUT_MOVF):
        self.broker = broker
        self.loop = loop

        # workers registration and timers
        self._workers = []
        self._worker_times = {}
        self.worker_timeout = worker_timeout
        self._runs = {}

        # local DB
        self._db = BrokerDB(self.loop, dbdir)

    @property
    def workers(self):
        return self._workers

    def _remove_worker(self, worker_id):
        logger.debug('%r removed' % worker_id)
        if worker_id in self._workers:
            self._workers.remove(worker_id)

        if worker_id in self._worker_times:
            del self._worker_times[worker_id]

        if worker_id in self._runs:
            del self._runs[worker_id]

    def register_worker(self, worker_id):
        if worker_id not in self._workers:
            self._workers.append(worker_id)
            logger.debug('%r registered' % worker_id)

    def unregister_worker(self, worker_id):
        if worker_id in self._workers:
            self._remove_worker(worker_id)

    def _associate(self, run_id, workers):
        when = time.time()

        for worker_id in workers:
            self._runs[worker_id] = run_id, when

    def reserve_workers(self, num, run_id):
        if num > len(self._workers):
            raise NotEnoughWorkersError('Not Enough workers')

        # we want to run the same command on several agents
        # provisionning them
        workers = []
        available = [wid for wid in self._workers if wid not in self._runs]

        while len(workers) < num:
            worker_id = random.choice(available)
            if self._check_worker(worker_id):
                workers.append(worker_id)
                available.remove(worker_id)

        self._associate(run_id, workers)
        return workers

    def send_to_worker(self, worker_id, msg):
        msg = list(msg)

        # start the timer
        self._worker_times[worker_id] = time.time(), None

        # now we can send to the right guy
        msg.insert(0, worker_id)
        try:
            self.broker._backstream.send_multipart(msg)
        except Exception, e:
            # we don't want to die on error. we just log it
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc = traceback.format_tb(exc_traceback)
            exc.insert(0, str(e))
            logger.error('\n'.join(exc))

    def clean(self):
        # XXX here we want to check out the runs
        # and cleanup _run given the status of the run
        # on each worker
        for worker_id, (run_id, when) in self._runs.items():
            status_msg = ['', json.dumps({'command': '_STATUS',
                                          'run_id': run_id})]
            self.send_to_worker(worker_id, status_msg)

    def update_status(self, worker_id, processes_status):
        now = time.time()

        if 'running' not in processes_status:
            # ended
            if worker_id in self._worker_times:
                del self._worker_times[worker_id]

            if worker_id in self._runs:
                del self._runs[worker_id]
        else:
            # not over
            if worker_id in self._worker_times:
                start, stop = self._worker_times[worker_id]
                self._worker_times[worker_id] = start, now
            else:
                self._worker_times[worker_id] = now, now

    #
    # DB APIs
    #
    def save_metadata(self, run_id, data):
        self._db.save_metadata(run_id, data)

    def get_metadata(self, run_id):
        return self._db.get_metadata(run_id)

    def save_data(self, worker_id, data):
        if worker_id in self._runs:
            data['run_id'], data['started'] = self._runs[worker_id]

        self._db.add(data)

    def get_data(self, run_id):
        return list(self._db.get_data(run_id))

    def get_counts(self, run_id):
        return self._db.get_counts(run_id)

    def _check_worker(self, worker_id):
        # box-specific, will do better later XXX
        exists = psutil.pid_exists(int(worker_id))
        if not exists:
            logger.debug('The worker %r is gone' % worker_id)
            self._remove_worker(worker_id)
            return False

        if worker_id in self._worker_times:
            start, stop = self._worker_times[worker_id]
            if stop is not None:
                duration = start - stop
                if duration > self.worker_timeout:
                    logger.debug('The worker %r is slow (%.2f)' % (worker_id,
                                                                   duration))
                    return False
        return True

    def list_runs(self):
        runs = defaultdict(list)
        for worker_id, (run_id, when) in self._runs.items():
            runs[run_id].append((worker_id, when))
        return runs

    def stop_run(self, run_id, msg):
        workers = []

        for worker_id, (_run_id, when) in self._runs.items():
            if run_id != _run_id:
                continue
            workers.append(worker_id)

        # now we have a list of workers to stop
        stop_msg = msg[:-1] + [json.dumps({'command': 'STOP'})]

        for worker_id in workers:
            self.send_to_worker(worker_id, stop_msg)

        self.clean()
        return workers

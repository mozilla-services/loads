import json
import os

from loads.transport.client import Client
import time


class ExecutionError(Exception):
    pass

class LoadsClient(Client):

    def execute(self, *args, **kw):
        res = Client.execute(self, *args, **kw)
        res = json.loads(res)
        if 'error' in res:
            raise ValueError(res['error'])
        return res['result']

    def run(self, args, async=True):
        # let's ask the broker how many agents it has
        res = self.execute({'command': 'LIST'})

        # do we have enough ?
        agents = len(res)

        if len(res) < args['agents']:
            raise ExecutionError('Not enough agents running on that broker')

        return self.execute({'command': 'SIMULRUN',
                             'async': async,
                             'agents': args['agents'],
                             'args': args})

    def status(self, worker_id):
        return self.execute({'command': 'STATUS', 'worker_id': worker_id})

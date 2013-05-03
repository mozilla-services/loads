import json
import os

from loads.transport.client import Client
import time

class LoadsClient(Client):

    def execute(self, *args, **kw):
        res = Client.execute(self, *args, **kw)
        res = json.loads(res)
        if 'error' in res:
            raise ValueError(res['error'])
        return res['result']

    def run(self, args, async=True):
        return self.execute({'command': 'RUN',
                             'async': async,
                             'args': args})

    def status(self, worker_id, pid):
        return self.execute({'command': 'STATUS', 'pid': pid, 'worker_id': worker_id})



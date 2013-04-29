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

    def run(self, fqnd, concurrency=1, numruns=1, async=True):
        return self.execute({'command': 'RUN',
                             'fqnd': fqnd,
                             'concurrency': concurrency,
                             'numruns': numruns,
                             'async': async})

    def status(self, worker_id, pid):
        return self.execute({'command': 'STATUS', 'pid': pid, 'worker_id': worker_id})



c = LoadsClient()


if os.path.exists('/tmp/testing'):
    os.remove('/tmp/testing')

res = c.run('loads.examples.test_blog.TestWebSite.test_something',
       concurrency=10, numruns=100)
pid = res['pid']
worker_id = res['worker_id']

status = c.status(worker_id, pid)
print status

while status == 'running':
    time.sleep(1.)
    status = c.status(worker_id, pid)
    print status


with open('/tmp/testing') as f:
    print f.read()


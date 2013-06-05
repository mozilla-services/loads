from loads.transport.util import DEFAULT_FRONTEND


def get_runner_args(fqn, users=1, cycles=1, agents=None,
                    broker=DEFAULT_FRONTEND, test_runner=None,
                    server_url='http://localhost:9000',
                    zmq_endpoint='tcp://127.0.0.1:5558', output='stdout'):

    return {'fqn': fqn,
            'users': str(users),
            'cycles': str(cycles),
            'agents': agents,
            'broker': broker,
            'test_runner': test_runner,
            'server_url': server_url,
            'zmq_endpoint': zmq_endpoint,
            'output': output}

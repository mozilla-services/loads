#! /usr/bin/python
import sys
import os

from loads.runners import LocalRunner
from loads.tests.support import get_runner_args


def main():
    fqn = sys.argv[1]
    status = [
        os.environ.get('LOADS_TOTAL_HITS', '1'),
        os.environ.get('LOADS_TOTAL_USERS', '1'),
        os.environ.get('LOADS_CURRENT_HIT', '1'),
        os.environ.get('LOADS_CURRENT_USER', '1'),
    ]
    args = get_runner_args(fqn=fqn,
                           hits=os.environ.get('LOADS_TOTAL_HITS'),
                           duration=os.environ.get('LOADS_DURATION'),
                           zmq_endpoint=os.environ['LOADS_ZMQ_RECEIVER'],
                           agent_id=os.environ['LOADS_AGENT_ID'],
                           run_id=os.environ['LOADS_RUN_ID'],
                           externally_managed=True,
                           loads_status=status, slave=True)
    LocalRunner(args).execute()


if __name__ == '__main__':
    main()

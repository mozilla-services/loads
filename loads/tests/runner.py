#! /usr/bin/python
import sys
import os

from loads.runner import Runner
from loads.tests.support import get_runner_args


def main():
    fqn = sys.argv[1]
    args = get_runner_args(fqn=fqn,
                           zmq_endpoint=os.environ['LOADS_ZMQ_RECEIVER'],
                           worker_id=os.environ['LOADS_WORKER_ID'],
                           slave=True)
    Runner(args).execute()


if __name__ == '__main__':
    main()

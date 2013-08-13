#! /usr/bin/python
import sys
import os

from loads.runners import LocalRunner
from loads.tests.support import get_runner_args


def main():
    fqn = sys.argv[1]
    status = os.environ['LOADS_STATUS'].split(',')
    args = get_runner_args(fqn=fqn,
                           zmq_endpoint=os.environ['LOADS_ZMQ_RECEIVER'],
                           agent_id=os.environ['LOADS_AGENT_ID'],
                           run_id=os.environ['LOADS_RUN_ID'],
                           externally_managed=True,
                           loads_status=status, slave=True)
    LocalRunner(args).execute()


if __name__ == '__main__':
    main()

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import time
import sys

from loads.util import logger, set_logger
from loads.case import TestCase


set_logger(True, logfile='stdout')


def _p(msg):
    sys.stdout.write(msg + '\n')
    logger.debug(msg)
    sys.stdout.flush()


def fail(job):
    _p('Starting loads.tests.jobs.fail')
    try:
        raise ValueError(job.data)
    finally:
        _p('Ending loads.tests.jobs.fail')


def timeout(job):
    _p('Starting loads.tests.jobs.timeout')
    time.sleep(2.)
    try:
        return job.data
    finally:
        _p('Ending loads.tests.jobs.timeout')


def timeout_overflow(job):
    _p('Starting loads.tests.jobs.timeout_overflow')
    time.sleep(job.data['age'])
    try:
        return str(job.data['age'])
    finally:
        _p('Ending loads.tests.jobs.timeout_overflow')


class SomeTests(TestCase):
    def test_one(self):
        pass

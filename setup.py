# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'README.rst')) as f:
    README = f.read()

with open(os.path.join(here, 'CHANGES.rst')) as f:
    CHANGES = f.read()


requires = ['pyzmq', 'psutil', 'gevent', 'requests']


setup(name='loads',
      version='0.1',
      packages=find_packages(),
      include_package_data=True,
      description='Implementation of the Request-Reply Broker pattern in ZMQ',
      long_description=README + '\n\n' + CHANGES,
      zip_safe=False,
      license='APLv2.0',
      classifiers=[
        "Programming Language :: Python",
      ],
      install_requires=requires,
      author='Mozilla Services',
      author_email='services-dev@mozilla.org',
      url='https://github.com/mozilla/loads',
      tests_require=['nose'],
      test_suite = 'nose.collector',
      entry_points="""
      [console_scripts]
      loads-broker = loads.transport.broker:main
      loads-worker = loads.transport.worker:main
      loads-cluster = loads.transport:main
      loads = loads.runner:main
      """)

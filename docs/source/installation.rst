.. _installation:

Installation
============

Prerequisites
-------------

**Loads** is developed and tested with Python 2.7.x and
Python 2.6.x. We encourage you to use the latest 2.7 version.

**Loads** uses ZeroMQ and Gevent, so you need to have libzmq and libev on
your system. You also need the Python headers.

Under Debuntu::

    $ sudo apt-get install libev-dev libzmq-dev python-dev

And under Mac OS X, using Brew::

    $ brew install libev
    $ brew install zeromq
    $ brew install python

Make sure you have a C compiler, and then pip::

    $ curl -O https://raw.github.com/pypa/pip/master/contrib/get-pip.py
    $ sudo python get-pip.py

This will install pip globally on your system.

The next step is to install Virtualenv::

    $ sudo pip install virtualenv

This will also install it globally on your system.


Basic installation
------------------

You can install **Loads** through Pip::

    $ pip install loads

Or build **Loads** from the Git repo::

    $ git clone https://github.com/mozilla-services/loads
    $ cd loads
    $ make build

This will compile Gevent 1.0rc2 using Cython, and all the dependencies
required by Loads - into a local virtualenv.

That's it. You should then find the **load-runner** command
in your bin directory.

Distributed
-----------

To install what's required to start a :term:`distributed run`,
it is encouraged to install Circus::

    $ pip install circus

Or if you build Loads from the source, simply run::

    $ make build_extras

Then you can read :ref:`distributed`.

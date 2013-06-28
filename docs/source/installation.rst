.. _installation:

Installation
============

Prerequisites
-------------

Loads uses ZeroMQ and Gevent, so you need to have libzmq and libev on
your system.

Under Debuntu::

    $ sudo apt-get install libev-dev libzmq-dev

And under Mac OS X, using Brew::

    $ brew install libev
    $ brew install zeromq


Make sure you have a C compiler, and then pip::

    $ curl -O https://raw.github.com/pypa/pip/master/contrib/get-pip.py
    $ sudo python get-pip.py

This will install pip globally on your system.

The next step is to install Virtualenv::

    $ sudo pip install virtualenv

This will also install it globally on your system.


Basic installation
------------------

Now we can build **Loads** locally::


    $ make build

This will compile Gevent 1.0rc2 using Cython, and all the dependencies
required by Loads - into a local virtualenv.

That's it. You should then find **load-runner** in your bin directory.

Distributed
-----------

To install what's required to run distributed tests, you need to
run::

    $ make build_extras


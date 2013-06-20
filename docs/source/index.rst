Welcome to Loads's documentation!
=================================

.. warning::

   Loads is under heavy development. Don't use it.



**Loads** is a framework for load testing an HTTP service.

Installation::

    $ bin/pip install loads


**Loads** works like Funkload: load tests are classical
Python unit tests that are calling the server(s) to tests
and a command line use them to run the actual load.


Instead of providing its own API to call the server to
test, **Loads** offers an integration with 3 existing
libraries: **Requests**, **WebTest** and **ws4py**.

Here's a test example::

    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_es(self):
            self.session.get('http://localhost:9200')


With such a test, running loads simply consists of doing::

    $ bin/loads-runner example.TestWebSite.test_es
    [======================================================================]  100%

    Hits: 1
    Started: 2013-06-14 12:15:42.860586
    Duration: 0.03 seconds
    Approximate Average RPS: 39
    Average request time: 0.01s
    Opened web sockets: 0
    Bytes received via web sockets : 0

    Success: 1
    Errors: 0
    Failures: 0


See :ref:`guide` for more options and information.



Background
----------

Loads is a client/server architecture based on ZMQ using a very
simple protocol.

It's heavily inspired by Funkload and the latest work
done there to add real-time capabilities. It's also now
quite similar to locust.io in the principles.

Each client performs load tests against a web application
and returns a json mapping to the server for each request made
against the app. Web sockets can also be load tested as
each client reports back every operation made with sockets
against an application.

The server collects the data and publishes them in a single
stream of data.

Since every interaction with the server is being done using
zmq & msgpack, the client can be built in any language.

**Loads** provides a built-in Python client based on the
*Requests* API.


More documentation
------------------

.. toctree::
   :maxdepth: 2

   guide
   internals
   zmq-api

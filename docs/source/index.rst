Welcome to Loads's documentation!
=================================

.. warning::

   Loads is under heavy development. Don't use it.



**Loads** is a framework for load testing an HTTP service.

Its installation is explained in :ref:`installation`.


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


More documentation
------------------

.. toctree::
   :maxdepth: 2

   installation
   guide
   internals
   zmq-api

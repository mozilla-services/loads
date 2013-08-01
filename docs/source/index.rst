Loads — Load testing for dummies
================================

**Loads** is a tool to load test your HTTP services.

With **Loads**, your load tests are classical
Python unit tests which are calling the service(s) you want to send load to.

It also comes with a command line to run the actual load.

Loads tries its best to avoid reinventing the wheel, so we offer integration
with 3 existing libraries: **Requests**, **WebTest** and **ws4py**.

Here's a really simple test example::

    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_es(self):
            self.session.get('http://localhost:9200')

If you don't want to write your load tests in python, or if you want to use any
other library to describe the testing, **Loads** allows you to use your
own formalism. see :doc:zmq-api.

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
   next-level
   internals
   zmq-api

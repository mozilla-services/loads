Loads — Load testing for dummies
================================

**Loads** is a tool to load test your HTTP services.

With **Loads**, your load tests are classical
Python unit tests which are calling the service(s) you want to send load to.

It also comes with a command line to run the actual load.

Loads tries its best to avoid reinventing the wheel, so we offer an
integration with 3 existing libraries: **Requests**, **WebTest** and
**ws4py**. You just need to write your tests with one
or several of those libraries, and **Loads** will do the rest.

Here's a really simple example where we check that a
local Elastic Search server is answering to HTTP calls:

.. code-block:: python

    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_es(self):
            res = self.session.get('http://localhost:9200')
            self.assertEqual(res.status_code, 200)


With such a test, running **Loads** is done by pointing the
*test_es* method:

.. code-block:: bash

    $ bin/loads-runner example.TestWebSite.test_es
    [===============================================]  100%

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

.. info::

   If you don't want to write your load tests using Python, or if
   you want to use any other library to describe the testing,
   **Loads** allows you to use your own formalism. See :ref:`zmq-api`.


More documentation
------------------

.. toctree::
   :maxdepth: 2

   installation
   guide
   next-level
   internals
   zmq-api
   glossary

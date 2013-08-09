Loads — Load testing for dummies
================================

.. figure:: logo.jpg
   :align: right
   :target: http://thenounproject.com/noun/riot/#icon-No15381

   by Juan Pablo Bravo

**Loads** is a tool to load test your HTTP services, including
web sockets.

With **Loads**, your load tests are classical
Python functional tests which are calling the service(s) you want to
exercise.

Loads is not asking you to use an ad-hoc API. The tool offers an
integration with 3 existing libraries: `Requests <http://docs.python-requests.org>`_,
`WebTest <http://webtest.readthedocs.org>`_ and
`ws4py <https://ws4py.readthedocs.org>`_.
You just need to write your tests using them, and **Loads**
will do the rest.

**Loads** can run tests from a single box or distributed across
many nodes, from the same command line tool. All tests results
are coming back to you in real time while the load is
progressing.

Since you are using Python to build your tests, you can
write very complex scenarii, and use **Loads** options to
run them using as many concurrent users as your hardware
(or cloud service) allows you.

Here's a really simple example where we check that a
local Elastic Search server is answering to HTTP calls:

.. code-block:: python

    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_es(self):
            res = self.session.get('http://localhost:9200')
            self.assertEqual(res.status_code, 200)


The test is also checking that the page is sending back a 200.
In case it's not behaving properly, **Loads** will let you know.


.. note::

   If you don't want to write your load tests using Python, or if
   you want to use any other library to write tests,
   **Loads** can be extended. See :ref:`zmq-api`.


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


See :ref:`guide` for a complete walkthrough. :ref:`commands`.
provides a detailed documentation on all the options you can
use.


More documentation
------------------

.. toctree::
   :maxdepth: 2

   installation
   guide
   commands
   distributed
   internals
   zmq-api
   glossary

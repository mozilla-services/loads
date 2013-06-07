Welcome to Loads's documentation!
=================================

.. warning::

   Loads is under heavy development. Don't use it.



**Loads** is a framework for load testing an HTTP service.

Installation::

    $ bin/pip install loads


Using Loads
-----------

**Loads** uses **Requests** and **WebTest**, in addition to Python unitest to
perform load tests.

Let's say you want to load test the Elastic Search root page on your
system.

Write a unittest like this one and save it in an **example.py** file::

    from loads.case import TestCase


    class TestWebSite(TestCase):

        def test_something(self):
            self.assertTrue('Search' in self.app.get('/'))

Another way to do it is to use the **Requests** *session* object, like this::

    def test_something(self):
        self.session.get('http://localhost:9200')


The *TestCase* class provided by loads sets a *session* object you can use
to interact with an HTTP server. It's a **Session** instance from Requests.

Now run **loads-runner** against it::

    $ bin/loads-runner example.TestWebSite.test_something --server_url http://localhost:9200
    [======================================================================]  100%

    Hits: 1
    Started: 2013-05-28 08:13:17.802290
    Duration: 0.00 seconds
    Approximate Average RPS: 0
    Opened web sockets: 0
    Bytes received via web sockets : 0

    Success: 1
    Errors: 0
    Failures: 0

This will execute your test just once - so you can control it works well.

Now try to run it using 100 virtual users, each of them running the test 10 times::

    $ bin/loads-runner example.TestWebSite.test_something -u 100 -c 10
    [======================================================================]  100%
    <unittest.result.TestResult run=1000 errors=0 failures=0>


Congrats, you've just sent a load of 1000 hits, using 100 concurrent threads.

Now let's run a cycle of 10, 20 then 30 users, each one running 20 hits::

    $ bin/loads-runner loads.examples.test_blog.TestWebSite.test_something -c 20 -u 10:20:30
    <unittest.result.TestResult run=1200 errors=0 failures=0>

That's 1200 hits total.


Using Web sockets
-----------------

**Loads** provides web sockets API through the **ws4py** library. You can
initialize a new socket connection using the **create_ws** method.

Run the echo_server.py file located in the examples directory, then
write a test that uses a web socket::


    import unittest
    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_something(self):
            def callback(m):
                results.append(m.data)

            ws = self.create_ws('ws://localhost:9000/ws',
                                callback=callback)
            ws.send('something')
            ws.receive()
            ws.send('happened')
            ws.receive()

            while len(results) < 2:
                time.sleep(.1)

            self.assertEqual(results, ['something', 'happened'])

XXX I'm actually unsure about the API we expose to test websockets. We should
have a look at how others do it


Using the cluster
=================

Install Circus::

    $ bin/pip install circus

And run it against **loads.ini**::

    $ bin/circusd --daemon loads.ini

Here is the content of the `loads.ini` file::

    [circus]
    check_delay = 5
    endpoint = tcp://127.0.0.1:5555
    pubsub_endpoint = tcp://127.0.0.1:5556
    stats_endpoint = tcp://127.0.0.1:5557
    httpd = 0
    debug = 0

    [watcher:broker]
    cmd = bin/loads-broker
    warmup_delay = 0
    numprocesses = 1

    [watcher:agents]
    cmd = bin/loads-agent
    warmup_delay = 0
    numprocesses = 5
    copy_env = 1

What happened? You have just started a Loads broker with 5 agents.

Let's use them now, with the **agents** option::

    $ bin/load-runner example.TestWebSite.test_something -u 10:20:30 -c 20 --agents 5
    [======================================================================]  100%

Congrats, you have just sent 6000 hits from 5 different agents.




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

**Loads** can be used within **Marteau**, a web
application that drives **Loads** and display realtime
reports.

More documentation
------------------

.. toctree::
   :maxdepth: 2

   internals



.. _guide:

Writing load tests
==================


Writing load tests can be done with Requests, WebTest or ws4py.
Loads provides a test case class that includes bridges to
the three libraries.

.. warning::

   Loads uses Gevent to spawn concurrent users. Most of the time,
   Gevent will play nicely with your tests and make sure that
   they are run asynchronously - but in case Loads is not
   sending the load it's supposed to, it probably means
   some of your code is blocking the Gevent loop.

   Read :ref:`async` to troubleshoot this issue.


Using Requests
--------------

`Requests <http://www.python-requests.org>`_ is a popular
library to query an HTTP service, and is widely used in the
Python community.

Let's say you want to load test the Elastic Search root page
that's running on your local host.

Write a test case like this one and save it in an **example.py** file::

    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_es(self):
            res = self.session.get('http://localhost:9200')
            self.assertEqual(res.status_code, 200)


The *TestCase* class provided by **Loads** has a *session* attribute you
can use to interact with an HTTP server. It's a **Session** instance
from Requests.

Now run **loads-runner** against it::

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


This will execute your test just once - so you can control that your test
works as expected.

Now, try to run it using 100 :term:`virtual users` (-u), each of them running the test
10 times (--hits)::

    $ bin/loads-runner example.TestWebSite.test_es -u 100 --hits 10
    [======================================================================]  100%
    Hits: 1000
    Started: 2013-06-14 12:15:06.375365
    Duration: 2.02 seconds
    Approximate Average RPS: 496
    Average request time: 0.04s
    Opened web sockets: 0
    Bytes received via web sockets : 0

    Success: 1000
    Errors: 0
    Failures: 0


Congrats, you've just sent a load of 1000 hits, using 100 virtual users.

Now let's run a series of 10, 20 then 30 users, each one running 20 hits::

    $ bin/loads-runner example.TestWebSite.test_something --hits 20 -u 10:20:30
    ...

That's 1200 hits total.

You can use all Requests API to GET, PUT, DELETE, POST or do whatever
you need on the service.

Don't forget to control all responses with assertions, so you can
catch any issue that may occur on your service on high load.

To do this, use the unit test `assert methods <http://docs.python.org/2/library/unittest.html#assert-methods>`_
provided by Python. Most services will break with 500s errors when they can't cope
with the load.


Using Loads with ws4py
----------------------

**Loads** provides web sockets API through the **ws4py** library. You can
initialize a new socket connection using the **create_ws** method provided
in the test case class.

Run the echo_server.py file located in Loads' examples directory, then
write a test that uses a web socket against it::


    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_something(self):

            results = []

            def callback(m):
                results.append(m.data)

            ws = self.create_ws('ws://localhost:9000/ws',
                                protocols=['chat', 'http-only'],
                                callback=callback)
            ws.send('something')
            ws.receive()
            ws.send('happened')
            ws.receive()

            while len(results) < 2:
                time.sleep(.1)

            self.assertEqual(results, ['something', 'happened'])

See `ws4py documentation <https://ws4py.readthedocs.org>`_
for more info.


Using Loads with WebTest
------------------------

If you are a **WebTest** fan, you can use it instead of Requests. If you don't
know what WebTest is, `you should have a look at it
<http://webtest.pythonpaste.org>`_ ;).

WebTest is really handy to exercise an HTTP service because it includes
tools to easily control the responses status code and content.

You just need to use **app** instead of **session** in the test case
class. **app** is a `webtest.TestApp` object, providing all the APIs to interact
with an HTTP service::

    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_something(self):
            self.assertTrue('tarek' in self.app.get('/'))


Of course, because the server root URL will change during the tests, you can
define it outside the tests, on the command line, with **--server-url**
when you run your load test::

    $ bin/loads-runner example.TestWebSite.test_something --server-url http://blog.ziade.org


Changing the server URL
~~~~~~~~~~~~~~~~~~~~~~~

It may happen that you need to change the server url when you're running the
tests. To do so, change the `server_url` attribute of the app object::

    self.app.server_url = 'http://new-server'



Adding custom metrics
---------------------

You can use the **incr_counter** method in your test case to increment a counter.
This is useful if you want to count the number of occurrences a particular event
happens.

In this example, the **tarek-was-there** counter will be incremented everytime
the test is successful::

    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_something(self):
            self.assertTrue('tarek' in self.app.get('/'))
            self.incr_counter('tarek-was-there')

At the end of the test, you will be able to know how many times the counter
was incremented.


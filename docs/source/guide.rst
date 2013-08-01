.. _guide:

User Guide
==========

Using Loads with Requests
-------------------------

Let's say you want to load test the Elastic Search root page on your
system, just to be sure.

Write a unittest like this one and save it in an **example.py** file::

    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_es(self):
            self.session.get('http://localhost:9200')


The *TestCase* class provided by **Load** has a *session* attribute you
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


This will execute your test just once - so you can control it works well.

Now, try to run it using 100 virtual users (-u), each of them running the test
10 times (-c)::

    $ bin/loads-runner example.TestWebSite.test_es -u 100 -c 10
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


Congrats, you've just sent a load of 1000 hits, using 100 concurrent threads.

Now let's run a series of 10, 20 then 30 users, each one running 20 hits::

    $ bin/loads-runner loads.examples.test_blog.TestWebSite.test_something --hits 20 -u 10:20:30

That's 1200 hits total.


Using Loads with ws4py
----------------------

**Loads** provides web sockets API through the **ws4py** library. You can
initialize a new socket connection using the **create_ws** method.

Run the echo_server.py file located in the examples directory, then
write a test that uses a web socket against it::


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



Using Loads with WebTest
------------------------

If you are a **WebTest** fan, you can use it instead of Requests. If you don't
know what webtest is, `you should have a look at it
<http://webtest.pythonpaste.org/en/latest/>`_ ;).

You just need to use **app** instead of **session** in the test class, that's
a `webtest.TestApp` object, providing all the APIs to interact with a web
application::

    from loads.case import TestCase

    class TestWebSite(TestCase):

        def test_something(self):
            self.assertTrue('Search' in self.app.get('/'))


Of course, because the server root URL will change during the tests, you can
define it outside the tests, on the command line, with **--server-url**
when you run your load test::

    $ bin/loads-runner example.TestWebSite.test_something --server_url http://localhost:9200



Changing the server URL
~~~~~~~~~~~~~~~~~~~~~~~

It may happen that you need to change the server url when you're running the
tests. To do so, change the `server_url` attribute of the app object::

    self.app.server_url = 'http://new-server'


Distributed test
----------------

If you want to send a lot of load, you need to run a distributed test.
A distributed test uses multiple agents to do the requests. The agents can be
on the same machine, or on a different physical hardware.

The **Loads** command line is able to interact with several **agents**
through a **broker**.

To run a broker and some agents, let's use Circus.

Install Circus::

    $ bin/pip install circus

And run it against the provided **loads.ini** configuration file that's
located in the Loads source repository in **conf**::

    $ bin/circusd --daemon conf/loads.ini

Here is the content of the `loads.ini` file::

    [circus]
    check_delay = 5
    httpd = 0
    statsd = 1
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

Congrats, you have just sent 6000 hits from 5 different agents. Easy, no?


Detach mode
~~~~~~~~~~~

When you are running a long test in distributed mode, you might want to detach
the console and come back later to check the status of the load test.

To do this, you can simply hit Ctrl+C. **Loads** will ask you if
you want to detach the console and continue the test, or simply stop it::


    [                                            ]   0%
    Duration: 2.04 seconds
    Hits: 964
    Started: 2013-07-22 07:12:30.139814
    Approximate Average RPS: 473
    Average request time: 0.00s
    Opened web sockets: 0
    Bytes received via web sockets : 0

    Success: 964
    Errors: 0
    Failures: 0

    Do you want to (s)top the test or (d)etach ? d


Then you can use **--attach** to reattach the console::

    $ bin/loads-runner --attach
    [                                       ]   4%
    Duration: 43.68 seconds
    Hits: 19233
    Started: 2013-07-22 07:12:30.144859
    Approximate Average RPS: 0
    Average request time: 0.00s
    Opened web sockets: 0
    Bytes received via web sockets : 0

    Success: 0
    Errors: 0
    Failures: 0

    Do you want to (s)top the test or (d)etach ? s


Running on Amazon Web Services
------------------------------

Running **Loads** on AWS requires you to have a dedicated AMI and security
group

**Loads** uses **boto** in order to provision new micro instances that will
be used as nodes to run the tests.

XXX

Outputs
-------

By default, loads reports the status of the load in real time onthe standard
output of the client machine. Depending what you are trying to achieve, that
may or may not be what you want.

**Loads** comes with a pluggable "output" mechanism: it's possible to
define your own output format if you need so.

You can change this behaviour with the --output option of the `loads-runner`
command line.

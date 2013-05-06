Loads
=====

.. warning::

   This is an untested, fast moving prototype


**Loads** is a framework for load testing an HTTP service.

Installation::

    $ bin/pip install loads


Using Loads
===========

**Loads** uses **Requests** and Python unitest to perform load tests.

Let's say you want to load test the Elastic Search root page on your
system.

Write a unittest like this one and save it in an **example.py** file::

    import unittest
    from loads import TestCase

    class TestWebSite(TestCase):

        def test_something(self):
            res = self.session.get('http://localhost:9200')
            self.assertTrue('Search' in res.content)


The *TestCase* class provided by loads sets a *session* object you can use
to interact with an HTTP server. It's a **Session** instance from Requests.


Now run **loads-runner** against it::

    $ bin/loads-runner example.TestWebSite.test_something
    [======================================================================]  100%
    <unittest.result.TestResult run=1 errors=0 failures=0>

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


Using the cluster
=================

Install Circus::

    $ bin/pip install circus

And run it against **loads.ini**::

    $ bin/circusd --daemon loads.ini

What happened ? You have just started a Loads broker with 5 agents.

Let's use them now, with the **agents** option::

    $ bin/load-runner example.TestWebSite.test_something -u 10:20:30 -c 20 --agents 5
    [======================================================================]  100%

Congrats, you have just sent 6000 hits from 5 different agents.


Reports
=======

realtime / vs static
XXX
XXX interaction shell, curl


Deploying the cluster on several slaves
=======================================

XXX


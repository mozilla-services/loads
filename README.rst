Loads
=====

**Loads** is a framework for load testing an HTTP service.

Installation::

    $ bin/pip install loads


Using Loads
===========

**Loads** uses **Requests** and Python unitest to perform load tests.

Let's say you want to load test the Elastic Search root page on your
system.

Write a unittest like this one::

    import unittest
    from loads import Session

    class TestWebSite(unittest.TestCase):

        def setUp(self):
            self.session = Session()

        def test_something(self):
            res = self.session.get('http://localhost:9200')
            self.assertTrue('Search' in res.content)


Now run **loads-runner** against it::

    $ bin/loads-runner loads.examples.test_blog.TestWebSite.test_something
    [======================================================================]  100%
    <unittest.result.TestResult run=1 errors=0 failures=0>

This will execute your test just once - so you can control it works well.

Now try to run it using 100 virtual users, each of them running the test 10 times:

    $ bin/loads-runner loads.examples.test_blog.TestWebSite.test_something -u 100 -c 10
    [======================================================================]  100%
    <unittest.result.TestResult run=1000 errors=0 failures=0>


Congrats, you just sent a load of 1000 hits, using 100 concurrent threads.


Using the cluster
=================

Install Circus::

    $ bin/pip install circus

And run it against **loads.ini**::

    $ bin/circusd --daemon loads.ini

What happened ? You have just started a Loads broker with 5 agents.

Let's use them now, with the **agents** option::

    $ bin/load-runner loads.examples.test_blog.TestWebSite.test_something -u 10 -c 10 --agents 5

Congrats, you have just sent 100 hits from 5 different agents.


Deploying the cluster on several slaves
=======================================

XXX


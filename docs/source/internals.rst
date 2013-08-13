Design
######

Hopefully, it's not really complicated to dig into the code and have a good
overview of how *Loads* is designed, but sometimes a good document explaining
how things are done is a good starting point, so let's try!

You can run Loads either in *distributed mode* or in *non-distributed* mode.
The vast majority of the time, you want to run several of agents to
hammer the service you want to load test. That's what we call
the *distributed mode*.

Alternatively, you may want to run things from a single process, just
to smoke test your service - or simply because you don't need
to send a huge load. That's the *non-distributed* mode.


What happens during a non-distributed run
=========================================


1. You invoke the `loads.runner.Runner` class.

2. A `loads.case.TestResult` object is created. This object is a data
   collector, it is passed to the test suite (`TestCase`), the loads `Session`
   object and the websocket manager. Its very purpose is to collect the data
   from these sources. You can read more in the section named `TestResult` below.

3. We create any number of outputs (standard output, html output, etc.) in the
   runner and register them to the test_result object.

4. The `loads.case.TestCase` derivated-class is built and we pass it the
   test_result object.

5. A number of threads / gevent greenlets are spawned and the tests are run one
   or multiple times.

6. During the tests, both the requests' `Session`, the test case itself and the
   websocket objects report their progress in real time to test_result. When
   there is a need to disambiguate the calls, a loads_status object is passed
   along.

   It contains data about the hits, the total number of users, the current
   user and the current hit.

7. Each time a call is made to the test_result object to add data, it notifies
   its list of observers to be sure they are up to date. This is helpful to
   create reports in real time, as we get data, and to provide a stream of info
   to the end users.

What happens during a distributed run
=====================================

When you run in distributed mode, you have a distributed runner (the
:term:`broker`) which defer the execution to one or several
:term:`agents`.

These agents are simple runners that will redirect their results
to the broker using a ZeroMQ stream.

The relay can be found in the `loads/relay.py` module. It's a
drop-in replacement for the *TestResult* class.

The broker gets back the results and store them in a database,
then publishes them in turn, so the caller can get them.

A schema might help you to get things right:

.. image:: loads.png


All the communication is handled through ZeroMQ sockets, as you can
see in the diagram.

In more details:

1. The distributed runner sends a message to the broker,
   asking it to run the tests on N agents.
2. The broker selects available agents and send them the job.
   Every agent starts a loads-runner instance in slave mode
3. The broker receives the results back from every agent.
4. The broker publishes the results so the distributed runner
   can get them.


The TestResult object
=====================

The TestResult object follows the APIs of unittest. That's why you can
use all assertions methods such as `addSuccess`, `addFailure`, etc.

Hopefully, people that are used to write Python tests should be familiar
with these API and they can use Loads' TestCase class in lieu of
the usual `unittest.TestCase class`.

Loads' `TestCase` class is located in `loads/case.py`, and implements
the same APIs than unittest's one.

The extra benefit of keeping our class compatible with unittest
is that you can also run Loads tests with third party test runners
like Nose or unittest2. They will be recognized as classical functional
tests.


The Runners
===========

As mentionned earlier, Loads is implemented with more than one Runner class.
Each of these classes share an implicit interface, allowing us to have more
than one implementation of a runner.

For instance, you can see that we have a `Runner` and a `DistributedRunner`.
The former is a "local" runner: it is able to runs the tests locally and
either proxy the results to a ZMQ backend or call its outputs with the results.

The latter, the `DistributedRunner` runs the tests on a Loads cluster, using
a :term:`broker` and one or more :term:`agents`.

A runner has a constructor, which takes an ``arg`` argument, a dict, with all
the useful options it may need. It is then started with the `execute` method.

If you want to add a specific behavior, you may need to subclass it and change
the `_execute` method (notice how it's prefixed with an underscore). This
method is where all the actual execution happens.
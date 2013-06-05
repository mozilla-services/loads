Under the hood — How loads is designed
######################################

Hopefully it's not really complicated to dig into the code and have a good
overview of how *loads* is designed, but sometimes a good document explaining
things is a good starting point, so let's try!

XXX Add a schema here explaining the broker / agents / distributed runner mode,
where the messages goes etc.

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
   
   It contains data about the cycles, the total number of users, the current
   user and the current cycle.

7. Each time a call is made to the test_result object to add data, it notifies
   its list of observers to be sure they are up to date. This is helpful to
   create reports in real time, as we get data, and to provide a stream of info
   to the end users.

What happens during a distributed run
=====================================

When you run in distributed mode, you have a distributed runner (master) which,
rather than running the tests locally, asks an `Agent` to run them. It is
possible to run a number of agents at the same time.

These agents are just simple runners, but instead of reporting everything
locally, using a *TestResult* object, they proxy all the data to the master
instance using a 0MQ stream.

It means that the code in `loads/proxy.py` is a drop-in replacement for
a TestResult object.

Once the results are back to the master, it populates its local *test_runner*,
which will in turn call the outputs to generate the reports.

The TestResult object
=====================

The TestResult object follows the APIs of unittest. That's why you can see
methods such as `addSuccess`, `addFailure`, etc.

It is done this way so that you actually can just replace the normal unittest
object by the one coming from loads, and gather data this way.

If you have a look at what you can find in `loads/case.py`, you will find that
we create a `TestResultProxy` object. This is done so that the test_result
object we pass to the TestCase have the exact same APIs than the one in
unittest (it used to contain extra arguments).

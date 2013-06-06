Under the hood — How loads is designed
######################################

Hopefully, it's not really complicated to dig into the code and have a good
overview of how *loads* is designed, but sometimes a good document explaining
things is a good starting point, so let's try!

You can run loads either in *distributed mode* or in *non-distributed* mode.
The vast majority of the time, you want to spawn a number of agents and let
them hammer the site you want to test. That's what we call the distributed
mode. Alternatively, you may want to run things in a single process, for
instance while writing your functional tests, that's the *non-distributed*
mode.


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
locally, using a *TestResult* object, they relay all the data to the master
instance using a 0MQ stream.

It means that the code in `loads/relay.py` is a drop-in replacement for
a TestResult object.

Once the results are back to the master, it populates its local *test_runner*,
which will in turn call the outputs to generate the reports.

A schema might help you to get things right::


    [ Distributed mode ]

                               /- Agent 1
    Loads-agent <--> broker ---
                               \- Agent 2


All the inter-process communications (IPC) are handled by ZeroMQ, as you can
see on the schema. Here is the caption:

1. The distributed loads runner (**the master**) sends a message to the broker,
   asking it to run the tests on N agents.
2. The broker selects the spare agents and send them the job
3. The agents start a loads-runner instance in slave mode (**the slave**),
   proxying all the calls to the `test_result` objects to the zmq push socket.
4. The **master** receives the calls and pass them to its local `test_results`
   instance.

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

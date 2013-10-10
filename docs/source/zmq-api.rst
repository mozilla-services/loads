.. _zmq-api:

Pluging-in external runners
###########################

Loads is built in a way which makes it possible to have tests
runners written in any language. To do that, it uses `ZeroMQ
<http://zeromq.org>`_ to do communication.

This document describes the protocol you need to implement if you want to
create your own runner.

Existing implementations
========================

Currently, there is only a Python implementation and a JavaScript
implementation. The JS runner is provided in a separate project named `loads.js
<https://github.com/mozilla-services/loads.js>`_.

If you have implemented your own runner, feel free to submit us a
patch or a pull request.

Using an external runner
========================

To instruct loads to use an external test runner, specify the path to the
executable in the **--test-runner** option like this::

    $ loads-runner --test-runner="./loadsjs/runner.js {test}" javascript_tests.js

The format variable `{test}` will be replaced with the fully-qualified test
name that is specified on the command-line.

The protocol
============

Loads will spawn one instance of the external runner process per user, per
cycle.  Details about the current cycle are passed in environment variables
as follows:

- **LOADS_ZMQ_RECEIVER**: The ZeroMQ endpoint to which all reporting and test
  result data should be sent.  This is the only channel for the runner to
  send data back to loads.

- **LOADS_AGENT_ID**: The id of the agent running these tests.  This is used
  to distinguish between results from multiple agents that may be reporting
  to a common broker.

- **LOADS_RUN_ID**: The unique id for the current run.  This is shared among
  all agents participating in a run, and used to distinguish between multiple
  runs being executed by a common broker.

- **LOADS_TOTAL_USERS**: The total number of users in the current cycle. This
  must be reported back as part of the loads_status field as described below.

- **LOADS_CURRENT_USER**: The particular user for which this process has been
  spawned. This must be reported back as part of the loads_status field as 
  described below.
  
- **LOADS_TOTAL_HITS**: The total number of hits to perform for this cycle.
  The runner must execute the specified tests this many times, and include the
  current hit number in the loads_status field a described below.

- **LOADS_DURATION**: The required duration of the cycle, in seconds.  If
  present then the runner must perform the tests in a loop until this many
  seconds have elapsed.
  

The **LOADS_TOTAL_HITS** and **LOADS_DURATION** variables define how many
runs of the tests should be performed, and are equivalent to the **--hits**
and **--duration** command-line arguments.  They are mutually exclusive.

The runner reports on its progress by sending messages to the specified ZeroMQ
endpoint.  Each message sent to Loads needs to respect the following rules:

- All the data is JSON encoded.
- Dates are expressed in `ISO 8601 format
  <https://en.wikipedia.org/wiki/ISO_8601>`_, (YYYY-MM-DDTHH:MM:SS)
- You should send along the agent id with every message. Each agent id should
  be different from each other.
- You should also send the id of the run.
- Additionally, each message contains a **data_type**, with the type of the
  data.

A message generally looks like this::

    {
        data_type: 'something',
        agent_id: '1',
        run_id: '1234',
        other_key_1: 'foo'
        other_key_2: 'bar'
    }


loads_status
------------

Some messages take a `loads_status` argument. `loads_status` is a list of
values concerning the current status of the load.

With loads, you can run cycle of runs. For instance, if you pass 10:50:100 for
the users, it will start with 10 users in parallel, and then 50 and finally
100.

Loads status contains information about the current number of users we have to
run for the cycle we are in (50, for instance), and the user we are currently
taking care of (could be 12). Same applies for the hits.

It contains, in this order:

- hits: the number of hits that will be running on this cycle.
- user: the number of users that will be running on this cycle.
- current_hit: the current hit we're running.
- current_user: the current user doing the requests.

errors / exceptions
-------------------

When errors / exceptions are caught, they are serialised and sent trough the
wire, as well. When you see an `exc *`, it is a list containing this:

- A string representation of the exception
- A string representation of the exception class
- The traceback / Stack trace.

Data types
==========

Tests
-----

When using Loads, you usually run a test suite. Tests start, stop, succeed and
fail. Here are the APIs you can use:

- addFailure(test_name, `exc *`, loads_status)
- addError(test_name, `exc *`, loads_status)
- addSuccess(test_name, loads_status)
- startTest(test_name, loads_status)
- stopTest(test_name, loads_status)

You should **not** send the `startTestRun` and `stopTestRun` messages.

Requests
--------

To track requests, you only have one method, named "add_hit" with the following parameters:

- `url`, the URL of the request, for instance http://notmyidea.org
- `method`, the HTTP method (GET, POST, PUT, etc.)
- `status`, the response of the call (200)
- `started`, the time when it started
- `elapsed`, the number of seconds (decimal) the request took to run
- loads_status, as already described

Sockets
-------

If you're also able to track what's going on with the socket connections, then
you can use the following messages:

- socket_open()
- socket_close()
- socket_message(size) # the size, in bytes, that were transmitted via the websocket.

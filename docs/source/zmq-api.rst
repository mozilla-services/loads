ZMQ APIs
########

Loads is built in a way that makes it possible to have runners written in
different languages. It's perfectly possible to have a runner in javascript or
ruby, sending data to loads.

This is made possible by the use of zeromq to send inter-process messages.

This means you can write your load tests with whatever language you want, as
long as the test-runner sends back its results in the zmq pipeline, respecting
the format described in this document.

Common bits
===========

The messages we send always contain a `data_type` key, which describes the type
of that that's being sent.

The messages respect the following rules:

- All the data is JSON encoded.
- Dates are expressed in ISO 8601 format, (YYYY-MM-DDTHH:MM:SS.mmmmmm)
- You should send along the worker with every message. Each worker id should be
  different from each other.

A message generally looks like this::
  
    {
        data_type: 'something',
        worker_id: WID
        worker_id: '1',
        other_key_1: 'foo'
        other_key_2: 'bar'
    }


loads_status
------------

Some messages take a `loads_status` argument. `loads_status` is a list of
values concerning the current status of the load. It contains, in this order:

- cycles: the number of cycles that will be running in total
- user: the number of users per cycle)
- current_cycle: the cycle we are currently in
- current_user: the current user that's doing the requests

errors / exceptions
-------------------

When errors / exceptions are caught, they are serialised and sent trough the
wire, as well. When you see an `exc *`, it is a list containing this:

- A string representation of the exception
- A string representation of the exception class
- The traceback / Stack trace.

Data types
==========

Before and after you run the tests, you need to tell that you're doing so:

- startTestRun()
- stopTestRun()


Tests
-----

When using loads, you usually run a test suite. Tests start, stop, succeed and
fail. Here are the APIs you can use:

- addFailure(test_name, `exc *`, loads_status)
- addError(test_name, `exc *`, loads_status)
- addSuccess(test_name, loads_status)
- startTest(test_name, loads_status)
- stopTest(test_name, loads_status)


Requests
--------

- add_hit(
      url, # http://notmyidea.org
      method, # GET
      http_status, # 200
      started, # the time when it started
      elapsed, # number of seconds (decimal) the request took
      loads_status)

Sockets
-------

- socket_open()
- socket_close()
- socket_message(size) # the size, in bytes, that were transmitted via the websocket.

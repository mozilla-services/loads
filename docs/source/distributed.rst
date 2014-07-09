.. _distributed:

Distributed test
================

.. warning::

   Loads comes with no security whatsoever. If you run
   a broker, make sure that you secure access to the box
   because any code can be executed remotely through the
   loads-runner command.

   The best way to avoid any issue is to protect the
   server access through firewall rules.


If you want to send a lot of load, you need to run a :term:`distributed test`.
A distributed test uses multiple :term:`agents` to do the requests.
The agents can be spread across several boxes called nodes.

A typical setup is to run a broker on a box, with a few agents, and
have dedicated boxes to run many agents. This setup is called
a **Loads cluster**.

The typical limiting factor will be the number of sockets each
box will be able to open on each node that will call your service.
This number can be tweaked by changing the **ulimit** value to
a higher number - like 8096. You can read this
`page <http://urbanairship.com/blog/2010/09/29/linux-kernel-tuning-for-c500k>`_
for more tips on tweaking your servers.


Setting up a Loads cluster
--------------------------

To run a broker and some agents, we can use
`Circus <http://circus.readthedocs.org>`_ - a process supervisor.

To install Circus you can use Pip::

    $ bin/pip install circus

If you have any trouble installing Circus, check out
its documentation.

Once Circus is installed, you can run it against
the provided **loads.ini** configuration file that's
located in the Loads source repository in the **conf/**
directory::

    $ bin/circusd --daemon conf/loads.ini

This command will run 1 broker and 5 agents

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


Let's control that the cluster is functional by pinging the broker
for its status::

    $ bin/loads-runner --ping-broker
    Broker running on pid 11154
    5 agents registered
    endpoints:
    - publisher: ipc:///tmp/loads-publisher.ipc
    - frontend: ipc:///tmp/loads-front.ipc
    - register: ipc:///tmp/loads-reg.ipc
    - receiver: ipc:///tmp/loads-broker-receiver.ipc
    - heartbeat: ipc:///tmp/hb.ipc
    - backend: ipc:///tmp/loads-back.ipc
    Nothing is running right now


Let's use them now, with the **agents** option, with the example
shown in :ref:`guide`::

    $ bin/load-runner example.TestWebSite.test_something -u 10:20:30 -c 20 --agents 5
    [======================================================================]  100%

Congrats, you have just sent 6000 hits from 5 different agents. Easy, no?

To stop your cluster::

    $ bin/circusctl quit

Adding more agents
------------------

XXX

Detach mode
-----------

When you are running a long test in distributed mode, you might want to detach
the console and come back later to check the status of the load test.

To do this, you can simply hit Ctrl+C. **Loads** will ask you if
you want to detach the console and continue the test, or simply stop it::


    $ bin/load-runner example.TestWebSite.test_something -u 10:20:30 -c 20 --agents 5
    ^C
    ...
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





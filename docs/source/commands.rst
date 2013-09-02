.. _commands:

Loads commands
==============

Loads comes with 3 commands:

1. **load-runner**: the test runner
2. **loads-broker**: the master when running in distributed mode
3. **loads-agent**: the slave when running in distributed mode


loads-runner
------------

loads-runner only mandatory argument is the *fully qualified name*
(FQN) of the test method you want to call. *Fully Qualified Name* means
that you provide a string that contains the package, sub packages,
module, class and test name, all separated by dots - like an
import statement.

For example, if your test module is called *test_server* and
located in the *tests* package under the *project* package,
the FQN for the *test_es* method in the *TestSite* class will be:
**project.tests.test_server.TestSite.test_es**.

Running that test is done with::

    $ loads-runner project.tests.test_server.TestSite.test_es


**Loads** imports the *test_server* module, instanciantes the
*TestSite* class, then call the *test_es* method.

Every other option in *loads-runner* is optional, as
the command provides defaults to run the test locally a single
time with a single user.

This is useful for trying out a test, but to do a real
load test, you will need more options.

Common options
::::::::::::::

Loads has 3 options you can use to define how much of
a load you are sending.

- **-u / --users**: the number of concurrent users spawned for
  the test. You can provide several values separated by ":".
  Example: "10:20:30". In that case, Loads will spawn 10, then
  20 then 30 users. That's what we call a **cycle**
  Defaults to 1.

- **--hits**: the number of times the test is executed per user.
  Like for **--users**, you can provide a *cycle*. The number
  of tests will be the cartesian product of hits by users.
  Defaults to 1.

- **-d / --duration**: number of seconds the test is run. This
  option is mutually exclusive with --hits. You will have to decide
  if you want to run test a certain number of times or for a
  certain amount of time. When using *duration*, Loads will
  loop on the test for each user indefinitely. Defaults
  to None.


Distributed mode options
::::::::::::::::::::::::


When running in distributed mode, the most important options
are **--broker** and **--agents**, that will let you point
a cluster and define the number of nodes to use, but they
are other options that may be useful to run your test.


- **-b / --broker**: Point to the broker's ZMQ front socket.
  defaults to *ipc:///tmp/loads-front.ipc*. We call it *front*
  socket because the broker has many other socket, and this
  one is used by the broker to receive all queries that are
  then dispatched to backends.

- **-a / --agents**: Defines the number of nodes you want to
  use to run a load test. This option triggers the distributed
  mode: if you use it, then *Loads* makes the assumption that
  you are in distributed mode. When you use agents, the
  users/hits/duration options will be sent to each agent, so
  the number of tests that will be executed is the cartesian
  product = [agents x users x (hits or duration)].
  Defaults to None.

- **--test-dir**: when provided, the broker will ask every agent
  to create the directory on the slave box, and chdir to it.
  For example, you can pass a value like "/tmp/mytest".
  Loads will create all intermediate directories if they don't
  exist.

- **--python-dep**: points a Python project name, that will be
  installed on each slave prior to running the test, using pip.
  You can provide the usual version
  notation if needed. You can also provide several *--python-dep*
  arguments if you need them - or None.

- **--include-file**: give that option a filename or a directory
  and Loads will recursively upload the files on each slave.
  That option needs to be used with *--test-dir*. You can
  also use glob-style patterns to include several files.
  Something like: "\*.py" will include all Python files
  in the current directory. Like *--python-deps** you
  can provide one or several options, or None.

- **--detach**: when this flag is used, the runner will
  call the broker and quit immediatly. The test will be
  running in detached mode. This can also be done
  by hitting Ctrl-C after the run has started.

- **--attach**: use this flag to reattach a console to
  an existing run. If several runs are active, you will
  have to choose which one to get attached to.

- **--ping-broker**: use this flag to display the broker
  status: the number of workers, the active runs
  and the broker options.

- **--purge-broker**: use this flag to stop all
  active runs.

- **--health-check**: use this flag to run an
  empty test on every agent. This option is useful
  to verify that every agent is up and responsive.

- **--observer**: you can point a fully qualified name
  that will be called from the broker when the test
  is over. *Loads* provides built-in observers: *irc*
  and *email*. They will send a message on a given
  channel or to a given recipient when the test
  is done.

- **--no-patching**: use this flag to prevent
  Gevent monkey patching. see :ref:`async` for
  more information on this.


Configuration file
::::::::::::::::::

Instead of typing a very long command line, you can create a configuration
file and have Loads use it.

Here's an example::


    [loads]
    fqn = example.TestWebSite.test_something
    agents = 4

    include_file = *.py
                pushtest

    test_dir = /tmp/tests
    users = 5
    duration = 30
    observer = irc
    detach = True


In this example, we're pushing a load test accross 4 agents.

Using this config file is done with the **--config** option::

    $ loads-runner --config config.ini



loads-broker
------------

XXX

loads-agent
-----------

XXX





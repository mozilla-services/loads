.. _glossary:

Glossary
========

.. glossary::
   :sorted:

   runner
     The code that will actually run the test suite for you.

   distributed run
   distributed test
     When a test is run in distributed mode, meaning that all the commands goes
     trought the broker and one or more agents.

   agent
     A process, running on a distant machine, waiting to run the tests (send
     the requests) to create some actual load on the system under test.

   system under test
     The website or service you want to test with Loads.

   broker
     The process which routes the jobs to the agents. It contains a broker
     controller and a broker database.

   observers
     Some python code in charge of notifying people via various channels (irc,
     email, etc.). Observers are running on the broker.

   outputs
     Some python code in charge of generating reports (in real time or not)
     about a Loads run. Outputs are running on the client side.

   workers
     Each agent can spawn a number of workers, which does the actual queries.
     The agent isn't sending itself the queries, it creates a worker which does
     it instead.

   virtual users
     When running a test, you can chose the number of users you want to have in
     parallel. This is called the number of virtual users.

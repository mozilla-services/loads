CHANGES
=======

0.8

0.7 - 2012-06-21
----------------

- auto-unregistring of dead/slow workers


0.6 - 2012-06-20
----------------

- introduced a graceful shutdown
- added a worker registering so restarting workers are not
  impacting the system

0.5 - 2012-06-12
----------------

- drastically reduced the number of used FDs, mainly by
  reusing the same context when possible


0.4 - 2012-05-25
----------------

- the broker exits if there's already a valid broker running
  in the socket.
- powerhose-broker gained 2 new options: --check and --purge-ghosts


0.3 - 2012-05-24
----------------

- implemented timeout_max_overflow in the client.
- the stacks are dumped on worker timeouts
- now using delayed callbacks for the heartbeat

0.2 - 2012-04-17
----------------

- make sure execution errors are properly transmited and raised.
- fixed the pool of connectors - so every connector is correctly freed
- now workers can get extra options from the command-line

0.1 - 2012-04-05
----------------

- initial release.


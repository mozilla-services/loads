CHANGES
=======

0.3 - 2014-05-22
----------------

- Agents id are now unique across boxes
- Disabling heartbeat on busy agents
- Busy agents cannot be killed that easily
- moved from a REP/ROUTER/REQ pattern to a REP/ROUTER/ROUTER
- Refactored Funkload output
- Refactored external runner interface
- Many more things

0.2 - 2013-09-27
----------------

- improved test coverage, distributed stability and documentation
- refactored the code in cleaner & smaller modules.
- 15% speedup for the broker
- Database backends are now plugins. We provide a pure Python disk-based one
  and a Redis one.
- extended the database API - now used in the loads-web project to display
  running load tests.
- the console can now be detached and also displays tracebacks.
- added several options: --duration, --ping-broker, --check-cluster,
  --no-patching
- Fixed the DNS resolving issues.
- Added support for multiple runs in external runners
- Added an experimental Funkload output

0.1 - 2013-08-02
----------------

- Initial release.

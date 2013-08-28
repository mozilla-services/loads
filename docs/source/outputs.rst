Outputs
=======

By default, Loads reports the status of the load in real time on the standard
output of the client machine. Depending what you are trying to achieve, that
may or may not be what you want.

**Loads** comes with a pluggable "output" mechanism: it's possible to
define your own output format if you need so.

You can change this behaviour with the --output option of the `loads-runner`
command line.

At the moment, we're supporting the following outputs:

- **file** if you want to have all the calls reported to a file. This is useful
  for later analysis but doesn't do much.
- **funkload** generates a funkload compatible report.
  These reports can then be used with the the `fl-build-report <filename>`
  command-line tool to generate reports about the load.
- **null** in case you want to silent the outputs.

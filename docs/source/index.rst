Welcome to Loads's documentation!
=================================

Contents:

.. toctree::
   :maxdepth: 2

**Loads** is a framework for load testing an HTTP service.


It's a client/server architecture based on ZMQ using a very simple
protocol.

It's heavily inspired by Funkload and the latest work
done there to add real-time capabilities. It's also now
quite similar to locust.io in the principles.

Each client performs load tests against a web application
and returns a json mapping to the server for each request made
against the app. Web sockets can also be load tested as
each client reports back every operation made with sockets
against an application.

The server collects the data and publishes them in a single
stream of data.

Since every interaction with the server is being done using
with zmq & msgpack, the client can be built in any language.

**Loads** provides a built-in Python client based on the
*Requests* API.

**Loads** can be used within **Marteau**, a web
application that drives **Loads** and display realtime
reports.



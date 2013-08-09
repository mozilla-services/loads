.. _async:

Writing asynchronous tests
==========================

When **loads-runner** is executing your tests, it calls
Gevent `monkey patching <http://www.gevent.org/gevent.monkey.html>`_
to make the Python standard library cooperative.

That feature works well when you are making classical
socket calls on a service, but some libraries are known
to be incompatible with this behavior.

If you encounter some issues, you can deactivate
the monkey patching with the **--no-patching** option
and work things out manually.


Asynchronous web sockets
------------------------

XXX

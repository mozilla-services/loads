Running Loads behind SSH
========================

If you deploy your cluster on a dedicated server, Loads does not
provide any security whatsoever on al the ZMQ sockets it binds.

The best way to secure your installation is to make sure the
sockets can't be reached from the outside world and use
ssh tunnelling to operate the cluster via **loads-runner**.

Let's say your cluster runs under the **tarek** user
on the **example.com** server. Create an alias in your ~/.ssh/config file
like this::


    Host loads-cluster
    	HostName example.com
    	User tarek
    	IdentityFile ~/.ssh/mykey.pem

Once this is done, make sure your broker runs on your server
with a TCP port for the frontend option and the publisher option::


    $ loads-broker --frontend tcp://0.0.0.0:7780 \
        --publisher tcp://0.0.0.0:7776

From there, running loads-runner is done by using the **ssh** option::

    $ loads-runner --shh tarek@loads-cluster ...

Loads will create an SSH tunnel for both sockets. You don't even need to
specify the **broker** option in case the two tunneled ports are
using the **7780** and **7776** ports. This are the default ports
Loads will try to tunnel in case you use the **ssh** option.



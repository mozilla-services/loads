import time

import zmq.green as zmq
from zmq.green.eventloop import ioloop, zmqstream

from loads.util import logger
from loads.transport.util import DEFAULT_HEARTBEAT


class Stethoscope(object):
    """Implements a ZMQ heartbeat client.

    Listens to a given ZMQ endpoint and expect to find there a beat.

    If no beat is found, it calls the :param onbeatlost: callable.
    When a beat is found, calls the :param onbeat: callable.

    Options:

    - **endpoint** : The ZMQ socket to call.
    - **warmup_delay** : The delay before starting to Ping. Defaults to 5s.
    - **delay**: The delay between two pings. Defaults to 3s.
    - **retries**: The number of attempts to ping. Defaults to 3.
    - **onbeatlost**: a callable that will be called when a ping failed.
      If the callable returns **True**, the ping quits. Defaults to None.
    - **onbeat**: a callable that will be called when a ping succeeds.
      Defaults to None.
    """
    def __init__(self, endpoint=DEFAULT_HEARTBEAT, warmup_delay=.5, delay=10.,
                 retries=3,
                 onbeatlost=None, onbeat=None, io_loop=None, ctx=None):
        self.loop = io_loop or ioloop.IOLoop.instance()
        self._stop_loop = io_loop is None
        self.daemon = True
        self.context = ctx or zmq.Context()
        self.endpoint = endpoint
        self.running = False
        self.delay = delay
        self.retries = retries
        self.onbeatlost = onbeatlost
        self.onbeat = onbeat
        self.warmup_delay = warmup_delay
        self._endpoint = None
        self._stream = None
        self._timer = None
        self.tries = 0

    def _initialize(self):
        logger.debug('Subscribing to ' + self.endpoint)
        self._endpoint = self.context.socket(zmq.SUB)
        self._endpoint.setsockopt(zmq.SUBSCRIBE, '')
        self._endpoint.linger = 0
        #self._endpoint.identity = str(os.getpid())
        self._endpoint.connect(self.endpoint)
        self._stream = zmqstream.ZMQStream(self._endpoint, self.loop)
        self._stream.on_recv(self._handle_recv)
        self._timer = ioloop.PeriodicCallback(self._delayed,
                                              self.delay * 1000,
                                              io_loop=self.loop)

    def _delayed(self):
        self.tries += 1
        if self.tries >= self.retries:
            logger.debug('Nothing came back')
            if self.onbeatlost is None or self.onbeatlost():
                self.stop()   # bye !

    def _handle_recv(self, msg):
        self.tries = 0
        if self.onbeat is not None:
            self.onbeat()
        logger.debug(msg[0])

    def start(self):
        """Starts the loop"""
        logger.debug('Starting the loop')
        if self.running:
            return
        self.running = True
        self._initialize()
        time.sleep(self.warmup_delay)
        self._timer.start()

    def stop(self):
        """Stops the Pinger"""
        logger.debug('Stopping the Pinger')
        self.running = False
        try:
            self._stream.flush()
        except zmq.ZMQError:
            pass

        self._timer.stop()


class Heartbeat(object):
    """Class that implements a ZMQ heartbeat server.

    This class sends in a ZMQ socket regular beats.

    Options:

    - **endpoint** : The ZMQ socket to call.
    - **interval** : Interval between two beat.
    """
    def __init__(self, endpoint=DEFAULT_HEARTBEAT, interval=10.,
                 io_loop=None, ctx=None):
        self.loop = io_loop or ioloop.IOLoop.instance()
        self.daemon = True
        self.kill_context = ctx is None
        self.context = ctx or zmq.Context()
        self.endpoint = endpoint
        self.running = False
        self.interval = interval
        logger.debug('Publishing to ' + self.endpoint)
        self._endpoint = self.context.socket(zmq.PUB)
        self._endpoint.linger = 0
        #self._endpoint.identity = b'HB'
        self._endpoint.hwm = 0
        self._endpoint.bind(self.endpoint)
        self._cb = ioloop.PeriodicCallback(self._ping, interval * 1000,
                                           io_loop=self.loop)

    def start(self):
        """Starts the Pong service"""
        self.running = True
        self._cb.start()

    def _ping(self):
        logger.debug('*beat*')
        self._endpoint.send('BEAT')

    def stop(self):
        """Stops the Pong service"""
        self.running = False
        self._cb.stop()
        if self.kill_context:
            self.context.destroy(0)

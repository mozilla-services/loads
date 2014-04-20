# -*- coding: utf-8 -*-
# -*- flake8: noqa -*-
from gevent import monkey; monkey.patch_all()

import argparse
import random
import os
import base64
import time

import gevent
import gevent.pywsgi

from ws4py.server.wsgiutils import WebSocketWSGIApplication
from ws4py.server.geventserver import WebSocketWSGIHandler, WSGIServer
from ws4py.websocket import EchoWebSocket


PAGE = """<html>
<head>
<script type='application/javascript' src='https://ajax.googleapis.com/ajax/libs/jquery/1.8.3/jquery.min.js'></script>
    <script type='application/javascript'>
    $(document).ready(function() {

        websocket = 'ws://%(host)s:%(port)s/ws';
        if (window.WebSocket) {
        ws = new WebSocket(websocket);
        }
        else if (window.MozWebSocket) {
        ws = MozWebSocket(websocket);
        }
        else {
        console.log('WebSocket Not Supported');
        return;
        }

        window.onbeforeunload = function(e) {
            $('#chat').val($('#chat').val() + 'Bye bye...\\n');
            ws.close(1000, '%(username)s left the room');

            if(!e) e = window.event;
            e.stopPropagation();
            e.preventDefault();
        };
        ws.onmessage = function (evt) {
            $('#chat').val($('#chat').val() + evt.data + '\\n');
        };
        ws.onopen = function() {
            ws.send("%(username)s entered the room");
        };
        ws.onclose = function(evt) {
            $('#chat').val($('#chat').val() + 'Connection closed by server: ' + evt.code + ' \"' + evt.reason + '\"\\n');
        };

        $('#send').click(function() {
            console.log($('#message').val());
            ws.send('%(username)s: ' + $('#message').val());
            $('#message').val("");
            return false;
        });
    });
    </script>
</head>
<body>
<form action='#' id='chatform' method='get'>
    <textarea id='chat' cols='35' rows='10'></textarea>
    <br />
    <label for='message'>%(username)s: </label><input type='text' id='message' />
    <input id='send' type='submit' value='Send' />
    </form>
</body>
</html>
"""

class PingWebSocket(EchoWebSocket):
    active = 0
    max = 0

    def opened(self):
        PingWebSocket.active += 1
        if PingWebSocket.max < PingWebSocket.active:
            PingWebSocket.max = PingWebSocket.active

    def closed(self, *args, **kw):
        PingWebSocket.active -= 1

    def received_message(self, m):
        self.send(m)
        gevent.sleep(0)


class EchoWebSocketApplication(object):
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.ws = WebSocketWSGIApplication(handler_cls=PingWebSocket)

    def active(self, environ, start_response):
        status = '200 OK'
        headers = [('Content-type', 'text/plain')]
        start_response(status, headers)
        return 'max: %d, current: %d' % (PingWebSocket.max, PingWebSocket.active)

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'] == '/active':
            return self.active(environ, start_response)

        if environ['PATH_INFO'] == '/favicon.ico':
            return self.favicon(environ, start_response)

        if environ['PATH_INFO'] == '/ws':
            environ['ws4py.app'] = self
            return self.ws(environ, start_response)

        if environ['PATH_INFO'] == '/auth':
            return self.auth(environ, start_response)

        return self.webapp(environ, start_response)

    def auth(self, environ, start_response):
        headers = [('Content-type', 'text/plain')]

        if 'HTTP_AUTHORIZATION' not in environ:
            start_response('401 Unauthorized', headers)
            return ['Unauthorized']

        status = '200 OK'
        start_response(status, headers)
        _auth = environ['HTTP_AUTHORIZATION'][6:]
        user, pwd = base64.b64decode(_auth).split(':')
        return user

    def webapp(self, environ, start_response):
        """
        Our main webapp that'll display the chat form
        """
        status = '200 OK'
        headers = [('Content-type', 'text/html')]

        start_response(status, headers)

        return PAGE % {'username': "User%d" % random.randint(0, 100),
                       'host': self.host,
                       'port': self.port}


class NoLog(object):
    def write(*args, **kw):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Echo gevent Server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('-p', '--port', default=9000, type=int)
    args = parser.parse_args()

    server = WSGIServer((args.host, args.port),
            EchoWebSocketApplication(args.host, args.port),
            log=NoLog(),
            backlog=100000)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

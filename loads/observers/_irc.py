import irc.client


class ExitError(Exception):
    pass


class IRCObserver(object):
    name = 'irc'
    options = [{'name': 'server', 'type': str, 'default': 'irc.mozilla.org'},
               {'name': 'channel', 'type': str, 'default': '#services-dev'},
               {'name': 'port', 'type': int, 'default': 8443},
               {'name': 'nickname', 'type': str, 'default': 'loads'}]

    def __init__(self, channel='#services-dev', server='irc.mozilla.org',
                 nickname='loads', port=8443, args=None, **kw):
        self.channel = channel
        self.server = server
        self.nickname = nickname
        self.port = port
        self.args = args

    def __call__(self, test_results):
        msg = 'Test over. %s' % str(test_results)

        # creating the IRC client
        client = irc.client.IRC()

        c = client.server().connect(self.server, self.port, self.nickname)

        def on_connect(connection, event):
            connection.join(self.channel)

        def on_endofnames(connection, event):
            main_loop(connection)

        def main_loop(connection):
            connection.privmsg(self.channel, msg)
            connection.quit("Bye !")

        def on_disconnect(connection, event):
            raise ExitError()

        def on_error(connection, event):
            raise ExitError()

        c.add_global_handler("welcome", on_connect)
        c.add_global_handler("endofnames", on_endofnames)
        c.add_global_handler("disconnect", on_disconnect)
        c.add_global_handler("error", on_error)

        try:
            client.process_forever()
        except ExitError:
            pass


if __name__ == '__main__':
    client = IRCObserver()
    client('ohay, I am the loads bot')

import ssl
import irc.client
import irc.connection


class ExitError(Exception):
    pass


class IRCObserver(object):
    name = 'irc'
    options = [{'name': 'server', 'type': str, 'default': 'irc.mozilla.org'},
               {'name': 'channel', 'type': str, 'default': '#services-dev'},
               {'name': 'port', 'type': int, 'default': 8443},
               {'name': 'ssl', 'type': bool, 'default': True},
               {'name': 'nickname', 'type': str, 'default': 'loads'}]

    def __init__(self, channel='#services-dev', server='irc.mozilla.org',
                 nickname='loads', port=8443, ssl=True, args=None, **kw):
        self.channel = channel
        self.server = server
        self.nickname = nickname
        self.port = port
        self.ssl = ssl
        self.args = args

    def __call__(self, test_results):
        msg = '[loads] Test Over. \x1f' + str(test_results)

        # creating the IRC client
        client = irc.client.IRC()

        if self.ssl:
            connect_factory = irc.connection.Factory(wrapper=ssl.wrap_socket)
        else:
            connect_factory = irc.connection.Factory()
        c = client.server().connect(self.server, self.port, self.nickname,
                                    connect_factory=connect_factory)

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

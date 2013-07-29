import irc.client
import irc.logging


class ExitError(Exception):
    pass


def send_irc(test_results, conf):
    msg = 'Test over. %s' % str(test_results)
    send_message('#services-dev', msg)


def send_message(channel, message, server='irc.mozilla.org',
                 nickname='loads', port=6667):
    client = irc.client.IRC()
    c = client.server().connect(server, port, nickname)

    def on_connect(connection, event):
        connection.join(channel)
        main_loop(connection)

    def on_join(connection, event):
        main_loop(connection)

    def main_loop(connection):
        connection.privmsg(channel, message)
        connection.quit("Bye !")

    def on_disconnect(connection, event):
        raise ExitError()

    c.add_global_handler("welcome", on_connect)
    c.add_global_handler("join", on_join)
    c.add_global_handler("disconnect", on_disconnect)

    try:
        client.process_forever()
    except ExitError:
        pass


if __name__ == '__main__':
    send_message('#services-dev', 'ohay, I am the loads bot')

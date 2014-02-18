from email.mime.text import MIMEText
from email.header import Header
from rfc822 import AddressList
import smtplib

from loads.util import logger


class EMailObserver(object):
    name = 'email'

    options = [{'name': 'sender', 'type': str, 'default': 'tarek@mozilla.com'},
               {'name': 'recipient', 'type': str,
                'default': 'tarek@mozilla.com'},
               {'name': 'host', 'type': str, 'default': 'localhost'},
               {'name': 'port', 'type': int, 'default': 25},
               {'name': 'user', 'type': str, 'default': None},
               {'name': 'password', 'type': str, 'default': None},
               {'name': 'subject', 'type': str, 'default': 'Loads Results'}]

    def _normalize_realname(self, field):
        address = AddressList(field).addresslist
        if len(address) == 1:
            realname, email = address[0]
            if realname != '':
                return '%s <%s>' % (str(Header(realname, 'utf-8')), str(email))
        return field

    def __init__(self, sender='tarek@mozilla.com', host='localhost', port=25,
                 user=None, password=None, subject='Loads Results',
                 recipient='tarek@mozilla.com', **kw):
        self.subject = subject
        self.sender = sender
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.recipient = recipient

    def __call__(self, test_results):
        # XXX we'll add more details in the mail later
        msg = 'Test over. %s' % str(test_results)
        body = msg

        msg = MIMEText(body.encode('utf-8'), 'plain', 'utf8')

        msg['From'] = self._normalize_realname(self.sender)
        msg['To'] = self._normalize_realname(self.recipient)
        msg['Subject'] = Header(self.subject, 'utf-8')

        logger.debug('Connecting to %s:%d' % (self.host, self.port))
        server = smtplib.SMTP(self.host, self.port, timeout=5)

        # auth
        if self.user is not None and self.password is not None:
            logger.debug('Login with %r' % self.user)
            try:
                server.login(self.user, self.password)
            except (smtplib.SMTPHeloError,
                    smtplib.SMTPAuthenticationError,
                    smtplib.SMTPException), e:
                return False, str(e)

        # the actual sending
        logger.debug('Sending the mail')
        try:
            server.sendmail(self.sender, [self.recipient], msg.as_string())
        finally:
            server.quit()


if __name__ == '__main__':
    client = EMailObserver()
    client('ohay, I am the loads bot')

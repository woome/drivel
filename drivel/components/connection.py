from eventlet import api
from eventlet import coros
import xmpp

from drivel.component import Component
#from drivel.green import xmpp

def plain_credentials(server):
    """basic credential func"""
    def get_credentials(user):
        return user.username, user.password
    return get_credentials


class XMPPSupervisor(Component):
    subscription = 'xmppc'
    message_pool_size = 10

    def __init__(self, server):
        self.server = server
        self.active_users = {}
        super(XMPPSupervisor, self).__init__(server)

    def _handle_message(self, event, message):
        method, user, tosend = message
        if user.username not in self.active_users:
            self.log('debug', 'user %s not found in existing- %s'
                % (user.username, ', '.join(i for i
                in self.active_users)))
            self.active_users[user.username] = XMPPConnection(
                self.server, user)
        self.active_users[user.username].send((event, method, tosend))

    def stats(self):
        stats = super(XMPPSupervisor, self).stats()
        stats.update({
            'xmppconnections:running': len(self.active_users),
        })
        return stats


class XMPPConnection(object):
    def __init__(self, server, user):
        self.server = server
        self.user = user
        self.client = None
        self._get_credentials = api.named(
            server.config.get('xmpp', 'credential_func')
        )(server)
        self._connected = coros.event()
        self._mqueue = coros.queue()
        api.spawn(self._connect)
        api.spawn(self._run)

    def _postconnection(self):
        self.client.RegisterHandler('default', self._default_handler)
        self.client.sendInitPresence()
        self._connected.send(True)
        self._process()

    def _process(self):
        while True:
            self.client.Process(1)

    def _run(self):
        self._connected.wait()
        while True:
            event, method, message = self._mqueue.wait()
            if method == 'send':
                if message:
                    if isinstance(message, (tuple, list)):
                        message = ''.join(message)
                    self.client.send(message)
            event.send()

    def send(self, message):
        self._mqueue.send(message)

    def _default_handler(self, session, stanza):
        self.server.log('XMPPConnection[%s]' % self.user.username,
            'debug', 'received stanza: %s' % stanza)
        self.server.send('history', 'set', self.user, stanza)

    def _connect(self):
        self.server.log('XMPPConnection[%s]' % self.user.username,
            'info', 'connecting...')
        domain = self.server.config.get('xmpp', 'domain')
        host = (self.server.config.has_section('xmpp') and
            self.server.config.has_option('xmpp', 'host') and
            self.server.config.get('xmpp', 'host'))
        port = (self.server.config.has_section('xmpp') and
            self.server.config.has_option('xmpp', 'port') and
            self.server.config.get('xmpp', 'port'))
        
        username, password = self._get_credentials(self.user)
        jid = xmpp.protocol.JID('%s@%s' % (username, domain))
        cl = xmpp.Client(jid.getDomain(), debug=[])
        secure = False
        condetails = (host or jid.getDomain(), port or 5222)
        assert cl.connect(
            condetails,
            secure=None if secure else 0
        ), "could not connect to %s:%s" % condetails 
        assert cl.auth(jid.getNode(), password), "could not authenticate"
        self.client = cl
        self.server.log('XMPPConnection[%s]' % self.user.username,
            'debug', '...connected')
        self._postconnection()


import time

from eventlet import api
from eventlet import event
from eventlet import proc
from eventlet import semaphore
from eventlet import queue
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

    def handle_message(self, message):
        method, user, tosend = message
        if user not in self.active_users:
            self.log('debug', 'user %s not found in existing connections' % user)
            self.active_users[user] = XMPPConnection(
                self.server, user)
            def remove(*args, **kwargs):
                self.log('debug', 'removing connection for %s' % user)
                del self.active_users[user]
                self.server.send('session', 'disconnected', user)
            self.active_users[user].link(remove)
        _event = event.Event()
        self.active_users[user].send((_event, method, tosend))
        return self.active_users[user].jid

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
        self._get_credentials = server.config.xmpp.import_('credential_func')(server)
        self._connected = event.Event()
        self._mqueue = queue.Queue()
        # Proc.spawn has the side-effect of not descheduling current coro which is what we
        # want here. (see assignment of instance into dict above)
        self._g_connect = proc.Proc.spawn(self._connect)
        self._g_run = proc.Proc.spawn(self._run)
        self._g_connect.link(self._g_run)
        self._last_activity = None
        self._inactivity_disconnect = server.config.xmpp.getint(
            'inactivity_disconnect')
        self._disconnect = False
        self._semaphore = semaphore.Semaphore(1)

    def link(self, to):
        self._g_run.link(to)

    @property
    def jid(self):
        self._connected.wait()
        c = self.client
        return "%s@%s/%s" % (c.User, c.Server, c.Resource)

    def _postconnection(self):
        self.client.RegisterDisconnectHandler(self._disconnect_handler)
        self.client.RegisterHandler('default', self._default_handler,
            system=True)
        self.client.RegisterHandler('presence', self._presence_handler,
            system=True)
        self.client.sendInitPresence()
        self._connected.send(True)
        self._process()

    def _process(self):
        while True:
            ret = api.trampoline(self.client.Connection._sock, read=True)
            if ret:
                self._handle_message(ret)
                api.call_after_global(0, self._g_run.greenlet.switch)
            else:
                # this semaphore stops the message queue greenlet from
                # switching into us whilst we're trying to read data
                self._semaphore.acquire()
                self.client.Process(1)
                self._semaphore.release()

    def _handle_message(self, message):
        event, method, message = message
        if method == 'send':
            self._last_activity = time.time()
            if message:
                if isinstance(message, (tuple, list)):
                    message = ''.join(message)
                self.client.send(message)
            event.send()
        elif method == 'disconnect':
            # check last activity
            if time.time() - self._last_activity > \
                    self._inactivity_disconnect:
                self._disconnect = True
                self.client.disconnect()
                event.send(True)
            else:
                # warning, there's been activity, abort
                event.send(False)
        else:
            event.throw(Exception('Unknown XMPP Method'))

    def _run(self):
        self._connected.wait()
        while True:
            message = self._mqueue.wait()
            self._semaphore.acquire()
            self._g_connect.greenlet.switch(message)
            self._semaphore.release()

    def send(self, message):
        self._mqueue.send(message)

    def _disconnect_handler(self, *args, **kwargs):
        if self._disconnect:
            # this seems to get fired twice for some reason
            self.server.log('XMPPConnection[%s]' % self.user.username,
                'debug', 'connection disconnected sucessfully')
            self._g_connect.kill()
            self._g_run.kill()
        else:
            self.server.log('XMPPConnection[%s]' % self.user.username,
                'warning', 'connection disconnected unexpetedly')
            self._g_connect.kill()
            self._g_run.kill()
        self.server.send('roster', 'conn-termination', self.user.username)

    def _default_handler(self, session, stanza):
        self.server.log('XMPPConnection[%s]' % self.user.username,
            'debug', 'received stanza: %s' % stanza)
        self.server.send('history', 'set', self.user, stanza)
    
    def _presence_handler(self, session, stanza):
        self.server.send('roster', 'presence', str(stanza))

    def _connect(self):
        self.server.log('XMPPConnection[%s]' % self.user.username,
            'info', 'connecting...')
        domain = self.server.config.xmpp.domain
        host = self.server.config.xmpp.get('host')
        port = self.server.config.xmpp.get('port')
        
        username, password = self._get_credentials(self.user)
        jid = xmpp.protocol.JID('%s@%s' % (username, domain))
        cl = xmpp.Client(jid.getDomain(), debug=[])
        secure = False
        condetails = (host or jid.getDomain(), port or 5222)
        assert cl.connect(
            condetails,
            secure=None if secure else 0
        ), "could not connect to %s:%s" % condetails 
        assert cl.auth(jid.getNode(), password, resource='httpgateway'), "could not authenticate"
        self.client = cl
        self.server.log('XMPPConnection[%s]' % self.user.username,
            'debug', '...connected')
        self._postconnection()


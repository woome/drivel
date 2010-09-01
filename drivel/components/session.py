from collections import defaultdict
from collections import deque
import uuid
# third-party imports
import eventlet
# local imports
from drivel.component import Component
from drivel.wsgi import ConnectionReplaced

# move to exceptions module to prevent circular imports
class SessionConflict(Exception):
    pass


class SessionManager(Component):
    subscription = 'session'
    def __init__(self, server, name):
        super(SessionManager, self).__init__(server, name)
        # list of all open connections for a session
        self.sessions = defaultdict(deque)
        # list of all sessions for a user
        self.user_sessions = defaultdict(set)
        # mapping sessid to user
        self.session_users = {}
        # timers for user inactivity
        self.user_timers = {}
        self._inactivity_disconnect = self.config.getint(('xmpp',
            'inactivity_disconnect'))

    def stats(self):
        stats = super(SessionManager, self).stats()
        stats.update({
            'sessions:activesessions': len(self.sessions),
            'sessions:connectedusers': len(self.user_sessions),
        })
        return stats

    def create(self):
        return uuid.uuid4().hex

    def cancel_inactivity_timer(self, user):
        if user in self.user_timers:
            self.log('debug', 'cancelling inactivity for %s' % user)
            self.user_timers[user].cancel()
            del self.user_timers[user]

    def _inactivity_alarm(self, user):
        self.log('debug', 'inactivity timer fired for %s' % user)
        del self.user_timers[user]
        # send message to xmppc to disconnect
        self.server.send('xmppc', 'disconnect', user, None).wait()

    def set_inactivity_timer(self, user):
        self.log('debug', 'setting inactivity timer for %s' % user)
        self.cancel_inactivity_timer(user)
        self.user_timers[user] = eventlet.spawn_after(self._inactivity_disconnect,
            self._inactivity_alarm, user)

    def remove_connection(self, sessid, conn):
        self.log('debug', 'removing session %s' % sessid)
        session = self.sessions[sessid]
        if conn in session:
            self.log('debug', 'session %s not found' % sessid)
            session.remove(conn)
        if not len(session):
            self.log('debug', 'no conns left in sessions %s' % sessid)
            del self.sessions[sessid]
            user = self.session_users.pop(sessid)
            uss = self.user_sessions[user]
            uss.remove(sessid)
            if not len(uss):
                self.log('debug', 'no sessions left for user %s' % user)
                del self.user_sessions[user]
                self.set_inactivity_timer(user)

    def disconnected_user(self, user):
        sessions = self.user_sessions.get(user, [])
        for session in sessions:
            for conn in self.sessions[session]:
                # need a new exception
                conn.kill(ConnectionReplaced())

    def add_connection(self, sessid, user, conn):
        self.log('debug', 'adding conn into sessions %s for user %s' %
            (sessid, user))
        if sessid in self.session_users:
            sess_user = self.session_users[sessid]
            if sess_user != user:
                raise SessionConflict("%s did not match owner of session %s"
                    ": %s" % (user, sessid, sess_user))
        else:
            self.session_users[sessid] = user
        self.user_sessions[user].add(sessid)
        self.sessions[sessid].append(conn)
        conn.link(lambda *args: self.remove_connection(sessid, conn))
        self.cancel_inactivity_timer(user)
        # terminate open connections
        while len(self.sessions[sessid]) > 1:
            g = self.sessions[sessid].popleft()
            if not g.dead:
                self.log('debug', 'terminating existing connection '
                    'for session %s' % sessid)
                g.kill(ConnectionReplaced())

    def handle_message(self, message):
        if message[0] == 'create':
            sessid = self.create()
            user, proc = message[1:]
            self.add_connection(sessid, user, proc)
            return sessid
        elif message[0] == 'register':
            user, sessid, proc = message[1:]
            self.add_connection(sessid, user, proc)
        elif message[0] == 'disconnected':
            user = message[1]
            self.disconnected_user(user)



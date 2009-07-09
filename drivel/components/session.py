from collections import defaultdict
from collections import deque
import uuid
# third-party imports
from eventlet import api
# local imports
from drivel.component import Component
from drivel.wsgi import ConnectionReplaced

class SessionManager(Component):
    subscription = 'session'
    def __init__(self, server):
        super(SessionManager, self).__init__(server)
        self.sessions = defaultdict(deque)
        self.user_sessions = defaultdict(set)

    def create(self):
        return uuid.uuid4().hex

    def _link_to_conn(self, conn, func, *args):
        # this will live here for now as we only link to 
        # the connection in one place currently.
        retg = api.getcurrent()
        def link(g, spawner, func, *args):
            g.parent = api.getcurrent()
            try:
                print 'linked to connection'
                spawner.switch()
            finally:
                print 'scheduling call'
                api.get_hub().schedule_call_global(0, func, *args)
        g = api.spawn(link, conn, retg, func, *args)
        g.switch()

    def remove_connection(self, sessid, conn):
        pass

    def add_connection(self, sessid, conn):
        self.sessions[sessid].append(conn)
        #self._link_to_conn(conn, self.remove_connection, sessid, conn)
        while len(self.sessions[sessid]) > 1:
            g = self.sessions[sessid].popleft()
            if not g.dead:
                self.log('debug', 'terminating existing connection '
                    'for session %s' % sessid)
                api.kill(g, ConnectionReplaced())

    def _handle_message(self, event, message):
        if message[0] == 'create':
            sessid = self.create()
            self.add_connection(sessid, message[1])
            event.send(sessid)
        if message[0] == 'register':
            sessid, grlet = message[1:]
            self.add_connection(sessid, grlet)


import collections
import time

import eventlet
from eventlet import greenthread
from eventlet import hubs
from eventlet import queue
from drivel.component import CancelOperation
from drivel.component import WSGIComponent

REMOVAL_HORIZON = 60 * 5 # 5mins
YIELD_AFTER = 10

class PushQueue(WSGIComponent):
    subscription = 'push'
    message_pool_size = 10000 
    urlmapping = {
        'listen': r'^/[^/]+/alerts/',
        'pushmsg': r'/(?P<username>[^/]+)/push/$',
        }

    def __init__(self, server, name):
        super(PushQueue, self).__init__(server, name)
        self.users = {}
        self.lruheap = collections.deque()
        self.lrudict = {}
        self.prune_greenthread = eventlet.spawn(self._prune_user_thread)

    def add_to_lru(self, username):
        t = time.time()
        self.lruheap.append((t, username))
        self.lrudict[username] = self.lrudict.get(username, 0) + 1

    def remove_users(self):
        unyielded_count = 0
        while self.lruheap and self.lruheap[0][0] + REMOVAL_HORIZON < time.time():
            addtime, username = self.lruheap.popleft()
            self.log('debug', 'removing user %s' % username)
            self.lrudict[username] -= 1
            if self.lrudict[username] == 0:
                del self.users[username]
                del self.lrudict[username]
            unyielded_count += 1
            if unyielded_count >= YIELD_AFTER:
                eventlet.sleep(0)
                unyielded_count = 0
        self.log('debug', 'remove done at %s. next at %s' % (
            time.time(),
            (self.lruheap and self.lruheap[0][0] + REMOVAL_HORIZON or '--')
        ))

    def _prune_user_thread(self):
        interval = 120
        while True:
            self.log('debug', 'user removal thread waking...')
            self.remove_users()
            eventlet.sleep(interval)

    def do_listen(self, user, request, proc):
        username = user.username
        cgt = greenthread.getcurrent()
        proc() and proc().link(self._dothrow, cgt)
        self.add_to_lru(username)
        try:
            q = self.users[username]
        except KeyError, e:
            q = queue.Queue()
            self.users[username] = q
        try:
            msg = [q.get()]
        except CancelOperation, e:
            return []
        try:
            while True:
                msg.append(q.get_nowait())
        except queue.Empty, e:
            pass
        return msg
        
    def do_pushmsg(self, user, request, proc, username):
        if not request.environ.get('woome.signed', False):
            return None
        if username in self.users:
            self.users[username].put(str(request.body))
        return []

    def stats(self):
        stats = super(PushQueue, self).stats()
        stats.update({
            'pushmessaging:waiting_users': len(self.users),
        })
        return stats


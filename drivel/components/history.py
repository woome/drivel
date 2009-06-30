from collections import defaultdict
from collections import deque
import time

from eventlet import coros

from ..component import Component

class History(Component):
    subscription = 'history'
    def __init__(self, server):
        super(History, self).__init__(server)
        self.history = defaultdict(list)
        self.waiters = defaultdict(deque)

    def get(self, user, since=None):
        if user.username in self.history and len(self.history[user.username]):
            msgs = [msg for msg in self.history[user.username]
                if since is None or msg[0] > since]
            return msgs
        return None

    def _handle_message(self, event, message):
        method, user, data = message
        if method == 'get':
            msgs = self.get(user, data)
            if not msgs:
                # wait for incoming
                self.log('debug', 'waiting for incoming messages '
                    'for user %s' % user.username)
                evt = coros.event()
                self.waiters[user.username].append(evt)
                evt.wait()
                self.log('debug', 'received notification of messages '
                    'for user %s' % user.username)
                msgs = self.get(user, data)
            event.send(msgs)
        elif method == 'set':
            self.history[user.username].append((time.time(), data))
            event.send()
            if user.username in self.waiters and len(
                self.waiters[user.username]):
                self.log('debug', 'waking up waiters for user %s'
                    % user.username)
                while len(self.waiters[user.username]):
                    waiter = self.waiters[user.username].popleft()
                    waiter.send()


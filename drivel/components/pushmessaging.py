from eventlet import queue
from drivel.component import WSGIComponent

class PushQueue(WSGIComponent):
    subscription = 'push'
    urlmapping = {
        'listen': r'^/[^/]+/alerts/',
        'pushmsg': r'/[^/]+/push/(?P<username>[^/]+)/$',
        }

    def __init__(self, server, name):
        super(PushQueue, self).__init__(server, name)
        self.users = {}

    def do_listen(self, user, request, proc):
        username = user.username
        try:
            q= self.users[username]
        except KeyError, e:
            q = queue.Queue()
            self.users[username] = q
        msg = q.get()
        return [msg]
        
    def do_pushmsg(self, user, request, proc, username):
        if username in self.users:
            self.users[username].put(str(request.body))
        return []

from eventlet import queue
from eventlet import greenthread
from drivel.component import WSGIComponent

def dothrow(gt, cgt):
    greenthread.kill(cgt)

class PushQueue(WSGIComponent):
    subscription = 'push'
    message_pool_size = 10000 
    urlmapping = {
        'listen': r'^/[^/]+/alerts/',
        'pushmsg': r'/[^/]+/push/(?P<username>[^/]+)/$',
        }

    def __init__(self, server, name):
        super(PushQueue, self).__init__(server, name)
        self.users = {}

    def do_listen(self, user, request, proc):
        username = user.username
        cgt = greenthread.getcurrent()
        proc.link(dothrow, cgt)
        try:
            q= self.users[username]
        except KeyError, e:
            q = queue.Queue()
            self.users[username] = q
        msg = [q.get()]
        try:
            while True:
                msg.append(q.get_nowait())
        except queue.Empty, e:
            pass
        return msg
        
    def do_pushmsg(self, user, request, proc, username):
        if username in self.users:
            self.users[username].put(str(request.body))
        return []

    def stats(self):
        stats = super(PushQueue, self).stats()
        stats.update({
            'pushmessaging:waiting_users': len(self.users),
        })
        return stats


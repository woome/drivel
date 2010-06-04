
import base64
import collections
import time
import hashlib
import uuid

try:
    import json
except ImportError:
    import simplejson as json

import eventlet
from eventlet import greenthread
from eventlet import hubs
from eventlet import patcher
from eventlet import queue
from drivel.component import CancelOperation, WSGIComponent
from drivel.utils import crypto
from drivel import wsgi

httplib2 = patcher.import_patched('httplib2')

REMOVAL_HORIZON = 60 * 5 # 5mins
YIELD_AFTER = 10


def dothrow(gt, cgt):
    hubs.get_hub().schedule_call_local(0,
        greenthread.getcurrent().switch)
    cgt.throw()


def uid():
    return base64.b64encode(uuid.uuid4().bytes, '-_').rstrip('=')


class PushQueue(WSGIComponent):
    subscription = 'push'
    message_pool_size = 10000 
    urlmapping = {
        'create': r'^/(?P<username>[^/]+)/create$',
        'delete': r'^/[^/]+/delete/(?P<secret>[^/]+)/(?P<sharedsecret>[^/]+)$',
        'listen': r'^/(?P<username>[^/]+)/alerts/(?P<secret>[^/]+)?(/(?P<sharedsecret>[^/]+))?$',
        'pushmsg': r'^/(?P<username>[^/]+)/push/(?P<sharedsecret>[^/]+)?$',
    }

    def __init__(self, server, name):
        super(PushQueue, self).__init__(server, name)
        self.users = {}
        self.lruheap = collections.deque()
        self.lrudict = {}
        self.prune_greenthread = eventlet.spawn(self._prune_user_thread)
        try:
            self.secret = server.config.crypto.secret
            self.secret = base64.b64decode(self.secret)
        except AttributeError:
            self.secret = None

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
                self.notify_closed(username)
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

# TODO is this needed?
#    def _user_offline(self, gt, cgt):
#        dothrow(gt, cgt)

    def notify_closed(self, username):
        """The client dropped the connection or timed out. Invoke callback.
        """
        if 'delete_callback' in self.users[username]:
            httplib2.Http().request(self.users[username]['delete_callback'], 'POST')

    def do_create(self, user, request, proc, username):
        body = request.body
        delete_callback = json.loads(request.body)['delete_callback']
        secret = uid()
        sharedsecret = uid()
        q = queue.Queue()
        self.users[username] = {
            'queue': q,
            'secret': secret,
            'sharedsecret': sharedsecret,
            'delete_callback': delete_callback
        }
        mac1 = crypto.b64encode(
            crypto.generate_mac(self.secret, username + sharedsecret))
        host = request.environ['HTTP_HOST']
        push_url = 'http://%(host)s/%(username)s/push/%(sharedsecret)s?mac=%(mac1)s' % locals()
        mac2 = crypto.b64encode(
            crypto.generate_mac(self.secret, username + secret + sharedsecret))
        poll_url = 'http://%(host)s/%(username)s/alerts/%(secret)s/%(sharedsecret)s?mac=%(mac2)s' % locals()

        return json.dumps(dict(push_url=push_url, poll_url=poll_url))

    def do_delete(self, user, request, proc, secret, sharedsecret):
        if not (self.users[username]['secret'] == secret and self.users[username]['sharedsecret'] == sharedsecret):
            return "['cannot delete: access denied']"
        del self.users[username]
        ## TODO Post back to some URL in chatty so we can remove this user
        ## from the queue or tell their partner they disconnected

    def do_listen(self, user, request, proc, username='', secret='', sharedsecret=''):
        username = user.username
        mac = request.GET.get('mac', '')
        if self.secret and not crypto.authenticate_mac(self.secret, str(username + secret + sharedsecret), crypto.b64decode(mac)):
            return ['listen: access denied, bad mac']
        cgt = greenthread.getcurrent()
        proc() and proc().link(dothrow, cgt)
        self.add_to_lru(username)            
        try:
            q = self.users[username]['queue']
            if self.users[username]['secret'] == secret:
                self.users[username]['sharedsecret'] = sharedsecret
            else:
                return ['listen: access denied, bad secret']
        except KeyError, e:
            if self.secret is not None:
                return ['listen: access denied, bad queue']
            q = queue.Queue()
            self.users[username] = {'queue': q, 'secret': secret, 'sharedsecret': sharedsecret}
        try:
            msg = [q.get()]
        except CancelOperation:
            eventlet.spawn(self.notify_closed, username)
            raise
        try:
            while True:
                msg.append(q.get_nowait())
        except queue.Empty, e:
            pass
        return msg

    def do_pushmsg(self, user, request, proc, username, sharedsecret=''):
        mac = request.GET.get('mac', '')
        if self.secret and not crypto.authenticate_mac(self.secret, str(username + sharedsecret), crypto.b64decode(mac)):
            return ['push: access denied bad mac']
        if not sharedsecret and not request.environ.get('woome.signed', False):
            return ['push: access denied: request not signed']
        if username in self.users:
            if self.users[username]['sharedsecret'] == sharedsecret:
                body = str(request.body) or request.GET.get('body')
                self.users[username]['queue'].put(body)
            else:
                return ['push: access denied, bad queue']
        return []

    def stats(self):
        stats = super(PushQueue, self).stats()
        stats.update({
            'pushmessaging:waiting_users': len(self.users),
        })
        return stats


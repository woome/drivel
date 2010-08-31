from functools import partial
import eventlet
from eventlet import queue
from eventlet import greenthread


class CancelOperation(Exception):
    pass


class Component(object):
    subscription = None
    asynchronous = True # spawn a coroutine for each message
    message_pool_size = 1000 # set to use a pool rather than coroutines

    def __init__(self, server, name=None):
        self.server = server
        self._mqueue = queue.Queue()
        assert self.subscription is not None
        self.server.subscribe(self.subscription, self._mqueue)
        self._greenlet = eventlet.spawn(self._process)
        self._coropool = None
        self.received_messages = 0
        self.handled_messages = 0
        self.num_errors = 0
        if self.asynchronous:
            poolsize = self.message_pool_size
            self._coropool = eventlet.GreenPool(size=poolsize)
            self._execute = self._coropool.spawn
        else:
            self._coropool = eventlet.GreenPool(size=1)
            self._execute = lambda func, *args: self._coropool.spawn(func, *args).wait()
        self.log = partial(self.server.log, self.__class__.__name__)
            
    @property
    def config(self):
        return self.server.config

    def _process(self):
        while True:
            event, message = self._mqueue.get()
            self.received_messages += 1
            self._execute(self._handle_message, event, message)
        
    def _handle_message(self, event, message):
        try:
            res = self.handle_message(message)
            self.handled_messages += 1
            event.send(res)
        except Exception, e:
            self.num_errors += 1
            event.send(exc=e)

    def handle_message(self, message):
        raise NotImplementedError()

    def stop(self):
        self._greenlet.throw()
        if self._coropool:
            self._coropool.killall()

    def stats(self):
        stats = {}
        if self._coropool:
            stats.update({
                'free': self._coropool.free(),
                'running': self._coropool.running(),
                'balance': self._coropool.sem.balance,
            })
        stats.update({
            'items': self._mqueue.qsize(),
            'handled': self.handled_messages,
            'received': self.received_messages,
            'errors': self.num_errors,
            'alive': bool(self._greenlet),
        })
        return stats

    def _dothrow(self, gt, cgt):
        #print 'throwing cancel from:%s to:%s current:%s' % (gt, cgt, greenthread.getcurrent())
        if isinstance(cgt, greenthread.GreenThread):
            cgt.kill(CancelOperation, None, None)
        else:
            hubs.get_hub().schedule_call_local(0,
                greenthread.getcurrent().switch)
            cgt.throw(CancelOperation())


class WSGIComponent(Component):
    urlmapping = None

    def __init__(self, server, name):
        super(WSGIComponent, self).__init__(server, name)
        self.active_messages = {}
        self.processed_messages = {}
        if self.urlmapping is None:
            # try and get from config
            try:
                self.urlmapping = self.config['%s-urlmappings' % name]
            except KeyError, e:
                raise NotImplementedError('no url provided')

        if isinstance(self.urlmapping, basestring):
            server.add_wsgimapping(self.urlmapping, self.subscription)
        elif isinstance(self.urlmapping, (tuple, list)):
            for m in self.urlmapping:
                server.add_wsgimapping(m, self.subscription)
        elif isinstance(self.urlmapping, dict):
            for k,v in self.urlmapping.iteritems():
                if isinstance(v, (tuple, list)):
                    for i in v:
                        server.add_wsgimapping((k, i), self.subscription)
                else:
                    server.add_wsgimapping((k,v), self.subscription)
        else:
            raise TypeError('Unknown type for WSGIComponent.urlmapping')

    def handle_message(self, message):
        msg, kw, args = message[0], message[1], message[2:]
        self.active_messages[msg] = self.active_messages.get(msg, 0) + 1
        self.processed_messages[msg] = self.processed_messages.get(msg, 0) + 1
        try:
            if msg is None:
                return self.do(*args, **kw)
            else:
                method = 'do_%s' % msg
                return getattr(self, method)(*args, **kw)
        finally:
            self.active_messages[msg] -= 1

    def stats(self):
        stats = super(WSGIComponent, self).stats()
        stats.update({
            'active_messages': self.active_messages,
            'processed_messages': self.processed_messages,
        })
        return stats



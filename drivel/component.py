from functools import partial
import eventlet
from eventlet import queue

class Component(object):
    subscription = None
    asynchronous = True # spawn a coroutine for each message
    message_pool_size = None # set to use a pool rather than coroutines

    def __init__(self, server, name=None):
        self.server = server
        self._mqueue = queue.Queue()
        assert self.subscription is not None
        self.server.subscribe(self.subscription, self._mqueue)
        self._greenlet = eventlet.spawn_n(self._process)
        self._coropool = None
        if self.asynchronous:
            poolsize = self.message_pool_size or 1000
            self._coropool = eventlet.GreenPool(max_size=poolsize)
            self._execute = self._coropool.spawn
        else:
            self._coropool = eventlet.GreenPool(max_size=1)
            self._execute = lambda func, *args: self._coropool.spawn(func, *args).wait()
        self.log = partial(self.server.log, self.__class__.__name__)
            
    @property
    def config(self):
        return self.server.config

    def _process(self):
        while True:
            event, message = self._mqueue.get()
            self._execute(self._handle_message, event, message)
        
    def _handle_message(self, event, message):
        try:
            res = self.handle_message(message)
            event.send(res)
        except Exception, e:
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
            'items': len(self._mqueue),
            'alive': bool(self._greenlet),
        })
        return stats

class WSGIComponent(Component):
    urlmapping = None

    def __init__(self, server, name):
        super(WSGIComponent, self).__init__(server, name)
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
        if msg is None:
            return self.do(*args, **kw)
        else:
            method = 'do_%s' % msg
            return getattr(self, method)(*args, **kw)


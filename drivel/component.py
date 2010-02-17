from functools import partial
import eventlet
from eventlet import pool
from eventlet import proc
from eventlet import queue

class Component(object):
    subscription = None
    asynchronous = True # spawn a coroutine for each message
    message_pool_size = None # set to use a pool rather than coroutines

    def __init__(self, server):
        self.server = server
        self._mqueue = queue.Queue()
        assert self.subscription is not None
        self.server.subscribe(self.subscription, self._mqueue)
        self._greenlet = eventlet.spawn_n(self._process)
        self._coropool = None
        self._procset = None
        if self.message_pool_size and self.asynchronous:
            self._coropool = pool.Pool(max_size=self.message_pool_size)
            self._execute = self._coropool.execute_async
        elif self.asynchronous:
            #self._execute = api.spawn
            self._procset = proc.RunningProcSet()
            self._execute = self._procset.spawn
        else:
            self._coropool = pool.Pool(max_size=1)
            self._execute = lambda func, *args: self._coropool.execute(func, *args).wait()
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
        elif self._procset:
            self._procset.killall()

    def stats(self):
        stats = {}
        if self._coropool:
            stats.update({
                'free': self._coropool.free(),
                'running': self._coropool.current_size,
                'balance': self._coropool.sem.balance,
            })
        elif self._procset:
            stats.update({
                'running': len(self._procset),
            })
        stats.update({
            'items': len(self._mqueue),
            'alive': bool(self._greenlet),
        })
        return stats


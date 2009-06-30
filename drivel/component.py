from functools import partial
from eventlet import api
from eventlet import coros
from eventlet import pool

class Component(object):
    subscription = None
    asynchronous = True # spawn a coroutine for each message
    message_pool_size = None # set to use a pool rather than coroutines

    def __init__(self, server):
        self.server = server
        self._mqueue = coros.queue()
        assert self.subscription is not None
        self.server.subscribe(self.subscription, self._mqueue)
        self._greenlet = api.spawn(self._process)
        self._coropool = None
        if self.message_pool_size:
            self._coropool = pool.Pool(max_size=self.message_pool_size)
            self._execute = self._coropool.execute_async
        elif self.asynchronous:
            self._execute = api.spawn
        else:
            self._execute = lambda func, *args: func(*args)
        self.log = partial(self.server.log, self.__class__.__name__)
            
    @property
    def config(self):
        return self.server.config

    def _process(self):
        while True:
            event, message = self._mqueue.wait()
            self._execute(self._handle_message, event, message)
        
    def _handle_message(self, event, message):
        raise NotImplementedError()

    def stop(self):
        self._greenlet.throw()


from eventlet import pools
from drivel.component import Component
from drivel.green import memcache

class _MemcachePool(pools.Pool):
    def __init__(self, pool_size, servers, *args, **kwargs):
        super(_MemcachePool, self).__init__(max_size=pool_size)
        self.servers = servers
        self.client_args = args
        self.client_kwargs = kwargs

    def create(self):
        return memcache.Client(self.servers,
            *self.client_args, **self.client_kwargs)


class ClientPool(Component):
    subscription = 'memcache'

    def __init__(self, server, name):
        super(ClientPool, self).__init__(server, name)
        poolsize = server.config.memcache.getint('pool_size')
        servers = [value for name, value
            in server.config['memcache-servers'].items()]
        self._pool = _MemcachePool(poolsize, servers)

    def handle_message(self, message):
        method = message[0]
        args = message[1:]
        client = self._pool.get()
        ret = getattr(client, method)(*args)
        self._pool.put(client)
        return ret

    def stats(self):
        stats = super(ClientPool, self).stats()
        stats.update({
            'memcacheclients:free': self._pool.free(),
            'memcacheclients:waiting': self._pool.waiting(),
        })
        return stats


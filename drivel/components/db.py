from ConfigParser import NoOptionError

from pg8000 import DBAPI
from eventlet import pools

from ..component import Component
#from .green.pg8000 import DBAPI

class _PgPool(pools.Pool):
    def __init__(self, pool_size, *args, **kwargs):
        super(_PgPool, self).__init__(max_size=pool_size)
        self.connection_args = args
        self.connection_kwargs = kwargs

    def create(self):
        return DBAPI.connect(*self.connection_args,
            **self.connection_kwargs)


def _getconf(server):
    keys = [
                'user',
                'host',
                'unix_sock',
                ('port', 'int'),
                'database',
                'password',
                'socket_timeout',
                ('ssl', 'boolean')
            ]
    for key in keys:
        if isinstance(key, tuple):
            key, method = key
        else:
            method = ''
        try:
            yield key, getattr(server.config, 'get%s' % method)('postgres', key)
        except NoOptionError, e:
            pass


class ConnectionPool(Component):
    subscription = 'db'

    def __init__(self, server):
        super(ConnectionPool, self).__init__(server)
        dbconf = dict(_getconf(server))
        poolsize = server.config.getint('postgres', 'pool_size')
        self._pool = _PgPool(poolsize, **dbconf)

    def _handle_message(self, event, message):
        query, params = message
        conn = self._pool.get()
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = list(cursor)
        self._pool.put(conn)
        event.send(result)

    def stats(self):
        stats = super(ConnectionPool, self).stats()
        stats.update({
            'dbconnections:free': self._pool.free(),
            'dbconnections:waiting': self._pool.waiting(),
        })
        return stats
        


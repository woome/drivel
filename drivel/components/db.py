from pg8000 import DBAPI
from eventlet import pools

from drivel.component import Component
#from drivel.green.pg8000 import DBAPI


# patch some pg8000 silliness.
# pg8000 issues a BEGIN instantly after commit or rollback
DBAPI.ConnectionWrapper.commit = lambda self: self.conn.commit()
DBAPI.ConnectionWrapper.rollback = lambda self: self.conn.rollback()
# create a begin method
DBAPI.ConnectionWrapper.begin = lambda self: self.conn.begin()

class _PgPool(pools.Pool):
    def __init__(self, pool_size, *args, **kwargs):
        super(_PgPool, self).__init__(max_size=pool_size)
        self.connection_args = args
        self.connection_kwargs = kwargs

    def create(self):
        conn = DBAPI.connect(*self.connection_args,
            **self.connection_kwargs)
        conn.rollback()  # close transaction that is automatically opened
        return conn


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
            yield key, getattr(server.config.postgres, 'get%s' % method)(key)
        except (KeyError, TypeError), e:
            pass


class ConnectionPool(Component):
    subscription = 'db'

    def __init__(self, server):
        super(ConnectionPool, self).__init__(server)
        dbconf = dict(_getconf(server))
        poolsize = server.config.postgres.getint('pool_size')
        self._pool = _PgPool(poolsize, **dbconf)

    def _handle_message(self, event, message):
        query, params = message
        conn = self._pool.get()
        cursor = conn.cursor()
        conn.begin()
        try:
            cursor.execute(query, params)
            result = list(cursor)
        except:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            self._pool.put(conn)
        event.send(result)
            

    def stats(self):
        stats = super(ConnectionPool, self).stats()
        stats.update({
            'dbconnections:free': self._pool.free(),
            'dbconnections:waiting': self._pool.waiting(),
        })
        return stats
        


"""A copy of the wsgi server included in eventlet.

The only change made is to include the coroutine pool as an attribute of
the Server isntance so that we can look at it and get stats of whether we
have waiting requests or not.

Also created a custom request handler (HttpProtocol) for sticking the socket
into the wsgi environment dict so that we can use it later for checking for
client termination of the connection.

"""
from eventlet.wsgi import *
EventletHttpProtocol = HttpProtocol

class HttpProtocol(EventletHttpProtocol):
    def get_environ(self):
        env = EventletHttpProtocol.get_environ(self)
        env['drivel.socket'] = self.request
        return env


def server(sock, site, log=None, environ=None, max_size=None, max_http_version=DEFAULT_MAX_HTTP_VERSION, protocol=HttpProtocol, server_event=None, minimum_chunk_size=None):
    serv = Server(sock, sock.getsockname(), site, log, environ=None, max_http_version=max_http_version, protocol=protocol, minimum_chunk_size=minimum_chunk_size)
    if max_size is None:
        max_size = DEFAULT_MAX_SIMULTANEOUS_REQUESTS
    pool = Pool(max_size=max_size)
    serv._pool = pool
    if server_event is not None:
        server_event.send(serv)
    try:
        host, port = sock.getsockname()
        port = ':%s' % (port, )
        if sock.is_secure:
            scheme = 'https'
            if port == ':443':
                port = ''
        else:
            scheme = 'http'
            if port == ':80':
                port = ''

        print "(%s) wsgi starting up on %s://%s%s/" % (os.getpid(), scheme, host, port)
        while True:
            try:
                try:
                    client_socket = sock.accept()
                except socket.error, e:
                    if e[0] != errno.EPIPE and e[0] != errno.EBADF:
                        raise
                p = pool.execute_async(serv.process_request, client_socket)
            except KeyboardInterrupt:
                print "wsgi exiting"
                break
    finally:
        try:
            sock.close()
        except socket.error, e:
            if e[0] != errno.EPIPE:
                traceback.print_exc()



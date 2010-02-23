import errno
from functools import partial
import os
import socket
import sys
import traceback
# third-party imports
import eventlet
from eventlet import greenthread
from eventlet import hubs
from eventlet import timeout
from webob import Request
# local imports
from auth import UnauthenticatedUser

class TimeoutException(Exception):
    pass

class InvalidSession(Exception):
    pass

class ConnectionReplaced(Exception):
    pass

class ConnectionClosed(Exception):
    pass

class PathNotResolved(Exception):
    pass

def _path_to_subscriber(routes, path):
    for s,k,r in routes:
        match = r.search(path)
        if match:
            kw = match.groupdict()
            return s, k, kw
    raise PathNotResolved(path)

def create_application(server):
    from components.session import SessionConflict # circular import
    authbackend = server.config.http.import_('auth_backend')(server)
    tsecs = server.config.http.getint('maxwait')
    log = partial(server.log, 'WSGI')
    # error handling
    def error_middleware(app):
        def application(environ, start_response):
            try:
                return app(environ, start_response)
            except UnauthenticatedUser, e:
                log('debug', 'request cannot be authenticated')
                start_response('403 Forbidden', [
                        ('Content-type', 'text/html'),
                    ], exc_info=sys.exc_info())
                return ['Could not be authenticated']
            except PathNotResolved, e:
                log('debug', 'no registered component for path')
                start_response('404 Not Found', [
                        ('Content-type', 'text/html'),
                    ], exc_info=sys.exc_info())
                return ['404 Not Found']
            except Exception, e:
                log('error', 'an unexpected exception was raised')
                log('error', traceback.format_exc())
                start_response('500 Internal Server Error', [
                        ('Content-type', 'text/html'),
                    ], exc_info=sys.exc_info())
                return ['Server encountered an unhandled exception']
        return application

    # coroutine stuff
    def linkablecoroutine_middleware(app):
        def application(environ, start_response):
            """run application in an coroutine that we can link and pass
            to application via wsgi environ so that it can use it.
            
            """
            proc = eventlet.spawn(app, environ, start_response)
            environ['drivel.wsgi_proc'] = proc
            return proc.wait()
        return application

    def watchconnection(sock, proc):
        """listen for EOF on socket."""
        def watcher(sock, proc):
            fileno = "%s" % (sock.fileno(),)
            try:
                log('debug', 'watching connection %s for termination'
                    ' at client end' % fileno)
                hubs.trampoline(sock, read=True)
                d = sock.read()
                if not d and bool(proc):
                    log('debug', 'terminating wsgi proc using closed sock %s' %
                        fileno)
                    greenthread.kill(proc, ConnectionClosed())
            except socket.error, e:
                if e[0] == errno.EPIPE:
                    log('debug', 'got broken pipe on sock %s. terminating.' % fileno)
                    greenthread.kill(proc, ConnectionClosed())
                else:
                    log('debug', 'got error %s for sock %' % (e, fileno))
            except IOError, e:
                if e.errno == errno.EPIPE:
                    log('debug', 'got broken pipe on sock %s. terminating.' % fileno)
                    greenthread.kill(proc, ConnectionClosed())
                else:
                    log('debug', 'got error %s for sock %' % (e, fileno))
            #except LinkedExited, e:
                #pass
        g = eventlet.spawn_n(watcher, sock, proc)
        #proc.link(g)

    # the actual wsgi app
    def application(environ, start_response):
        # webob can change this, so get it now!
        rfile = getattr(environ['wsgi.input'], 'rfile', None)
        request = Request(environ)
        proc = environ['drivel.wsgi_proc']
        if request.method not in ['GET', 'POST']:
            start_response('405 Method Not Allowed', [('Allow', 'GET, POST')])
            return ['']
        elif request.path == '/ping':
            start_response('200 OK', [('Content-type', 'text/plain')])
            return ['pong']
        elif request.path == '/favicon.ico':
            start_response('404 Not Found', [])
            return ['']
        user = authbackend(request)
        path = request.path.strip('/').split('/')
        #body = str(request.body) if request.method == 'POST' else ''

        try:
            timeouttimer = timeout.Timeout(tsecs, TimeoutException())
            if rfile:
                watchconnection(rfile, proc)
            subs, msg, kw = _path_to_subscriber(server.wsgiroutes, request.path)
            msgs = server.send(subs, msg, kw, user, request, proc).wait()
        except TimeoutException, e:
            log('debug', 'timeout reached for user %s' % user)
            msgs = []
        except ConnectionClosed, e:
            log('debug', 'connection closed for user %s' % user)
            msgs = []
        finally:
            timeouttimer.cancel()
        # do response
        log('debug', 'got messages %s for user %s' % (msgs, user))
        start_response('200 OK', [('Content-type', 'text/xml')])
        if isinstance(msgs, basestring):
            return [msgs]
        elif msgs is None:
            return ['']
        else:
            return ['\n'.join(msgs) if msgs else '']

    app = error_middleware(application)
    app = linkablecoroutine_middleware(app)
    return app


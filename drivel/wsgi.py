import errno
from functools import partial
import os
import socket
import sys
import traceback
# third-party imports
import eventlet
from eventlet import api
from eventlet.proc import LinkedExited
from eventlet.proc import Proc
from lxml import etree
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
            except etree.XMLSyntaxError, e:
                log('debug', 'received malformed body from client')
                start_response('400 Bad Request', [
                        ('Content-type', 'text/html'),
                    ], exc_info=sys.exc_info())
                return ['Could not parse POST body']
            except InvalidSession, e:
                log('debug', 'received unparsable or invalid session')
                start_response('404 Not Found', [
                        ('Content-type', 'text/html'),
                    ], exc_info=sys.exc_info())
                return ['Invalid session url']
            except SessionConflict, e:
                log('debug', 'received session id owned by another user')
                start_response('403 Forbidden', [
                        ('Content-type', 'text/html'),
                    ], exc_info=sys.exc_info())
                return ['Invalid session url for user']
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
                api.trampoline(sock, read=True)
                d = sock.read()
                if not d and bool(proc):
                    log('debug', 'terminating wsgi proc using closed sock %s' %
                        fileno)
                    proc.kill(ConnectionClosed())
            except socket.error, e:
                if e[0] == errno.EPIPE:
                    log('debug', 'got broken pipe on sock %s. terminating.' % fileno)
                    proc.kill(ConnectionClosed())
                else:
                    log('debug', 'got error %s for sock %' % (e, fileno))
            except IOError, e:
                if e.errno == errno.EPIPE:
                    log('debug', 'got broken pipe on sock %s. terminating.' % fileno)
                    proc.kill(ConnectionClosed())
                else:
                    log('debug', 'got error %s for sock %' % (e, fileno))
            except LinkedExited, e:
                pass
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
        if path[1:2] and path[1] == 'session':
            try:
                sessionid = path[2]
                assert len(sessionid) == 32
                assert long(sessionid, 16)
                log('debug', 'request had existing session: %s' % sessionid)
                server.send('session', 'register', user, sessionid, proc)
            except (ValueError, IndexError, AssertionError), e:
                raise InvalidSession()
        else:
            sessionid = server.send('session', 'create', user, proc).wait()
            log('debug', 'created new session for request: %s' % sessionid)
        log('debug', 'handling %s for user %s' % (request.method, user.username))
        tosend = []
        if request.method == 'POST' and request.body:
            # need error handling here
            tree = etree.fromstring(request.body)
            if tree.tag == 'body':
                tosend = map(etree.tostring, tree.getchildren())
        jid = server.send('xmppc', 'send', user, tosend).wait()
        since = (float(request.GET.getone('since'))
            if 'since' in request.GET else None) # can raise exception
        try:
            timeout = api.exc_after(tsecs, TimeoutException())
            if rfile:
                watchconnection(rfile, proc)
            msgs = server.send('history', 'get', user, since).wait()
        except TimeoutException, e:
            log('debug', 'timeout reached for user %s' % user)
            msgs = []
        except ConnectionReplaced, e:
            log('debug', 'connection replaced for user %s' % user)
            msgs = []
        except ConnectionClosed, e:
            log('debug', 'connection closed for user %s' % user)
            msgs = []
        finally:
            timeout.cancel()
        # do response
        log('debug', 'got messages %s' % msgs)
        start_response('200 OK', [('Content-type', 'text/xml')])
        response = []
        maxtime = since or 0
        for t, msg in msgs:
            response.append(msg)
            maxtime = max(maxtime, t)
        opentag = '<body upto="%s" jid="%s" session="%s">' % (repr(maxtime),
            jid, sessionid)
        log('debug', 'sending response -- bodytag: %s' % opentag)
        return [''.join([opentag,
            "".join(map(str, response)),
            '</body>'])]

    app = error_middleware(application)
    app = linkablecoroutine_middleware(app)
    return app


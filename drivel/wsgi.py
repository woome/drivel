from functools import partial
import sys
import traceback
# third-party imports
from eventlet import api
from lxml import etree
from webob import Request
# local imports
from auth import UnauthenticatedUser

class TimeoutException(Exception):
    pass

def create_application(server):
    authbackend = server.config.get('http', 'auth_backend')
    authbackend = api.named(authbackend)(server)
    tsecs = server.config.getint('http', 'maxwait')
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
            except Exception, e:
                log('error', 'an unexpected exception was raised')
                log('error', traceback.format_exc())
                start_response('500 Internal Server Error', [
                        ('Content-type', 'text/html'),
                    ], exc_info=sys.exc_info())
                return ['Server encountered an unhandled exception']
        return application

    # the actual wsgi app
    def application(environ, start_response):
        request = Request(environ)
        if request.method not in ['GET', 'POST']:
            start_response('405 Method Not Allowed', [('Allow', 'GET, POST')])
            return ''
        user = authbackend(request)
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
            msgs = server.send('history', 'get', user, since).wait()
        except TimeoutException, e:
            server.log('wsgi.application', 'debug',
                'timeout reached for user %s' % user.username)
            msgs = []
        else:
            timeout.cancel()
        # do response
        log('debug', 'got messages %s' % msgs)
        start_response('200 OK', [('Content-type', 'text/xml')])
        response = []
        maxtime = since or 0
        for t, msg in msgs:
            response.append(msg)
            maxtime = max(maxtime, t)
        opentag = '<body upto="%s" jid="%s">' % (repr(maxtime), jid)
        log('debug', 'sending response -- bodytag: %s' % opentag)
        return [''.join([opentag,
            "".join(map(str, response)),
            '</body>'])]
    return error_middleware(application)


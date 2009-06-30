from eventlet import api
from webob import Request

class TimeoutException(Exception):
    pass

def create_application(server):
    authbackend = server.config.get('http', 'auth_backend')
    authbackend = api.named(authbackend)(server)
    tsecs = server.config.getint('http', 'maxwait')
    # the actual wsgi app
    def application(environ, start_response):
        request = Request(environ)
        user = authbackend(request)
        tosend = []
        if request.method == 'POST':
            pass
        server.send('xmppc', 'send', user, tosend)
        since = (request.GET.getone('since') 
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
        start_response('200 OK', [('Content-type', 'text/xml')])
        response = []
        maxtime = since or 0
        for t, msg in msgs:
            response.append(msg)
            maxtime = max(maxtime, t)
        return ['<body upto="%s">' % maxtime, "".join(map(str, response)), '</body>']
    return application


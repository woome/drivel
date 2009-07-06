from ..auth import User
from ..auth import UnauthenticatedUser

def MemcacheAuthBackend(server):
    session_cookie = server.config.get('http', 'session_cookie')
    def doauth(request):
        sessionid = request.cookies.get(session_cookie)
        session = server.send('memcache', 'get', sessionid).wait()
        userid = session.get('_auth_user_id')
        cachekey = 'user_object_for_id_%s' % userid
        cachehit = server.send('memcache', 'get', cachekey).wait()
        if cachehit:
            return cachehit
        rows = server.send('db', 'SELECT username, password FROM auth_user '
            'WHERE id = %s', [userid]).wait()
        if not rows:
            raise UnauthenticatedUser()
        user = User(userid, *rows[0])
        server.send('memcache', 'set', cachekey, user)
        return user
    return doauth


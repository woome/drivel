class User(object):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

def MemcacheAuthBackend(server):
    session_cookie = server.config.get('http', 'session_cookie')
    def doauth(request):
        sessionid = request.cookies.get(session_cookie)
        session = server.send('memcache', 'get', sessionid).wait()
        userid = session.get('_auth_user_id')
        rows = server.send('db', 'SELECT username, password FROM auth_user '
            'WHERE id = %s', [userid]).wait()
        return User(userid, *rows[0])
    return doauth


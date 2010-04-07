import base64
import cPickle as pickle
from datetime import datetime
from hashlib import md5

from drivel.auth import User
from drivel.auth import UnauthenticatedUser
from drivel.contrib import username_from_path

def decode(session_data, secret_key):
    """Decode django session serialisation from db.

    Taken from django.contrib.session.backends.base.SessionBase

    """
    encoded_data = base64.decodestring(session_data)
    pickled, tamper_check = encoded_data[:-32], encoded_data[-32:]
    if md5(pickled + secret_key).hexdigest() != tamper_check:
        raise UnauthenticatedUser() # was SuspiciousOperation
    try:
        return pickle.loads(pickled)
    # Unpickling can cause a variety of exceptions. If something happens,
    # just return an empty dictionary (an empty session).
    except:
        return {}


def URLAuthBackend(server):
    def doauth(request):
        un = username_from_path(request.path)
        rows = server.send('db',
            'SELECT id, password FROM auth_user WHERE username = %s', [un]).wait()
        if rows:
            return User(rows[0][0], un, rows[0][1])
        raise UnauthenticatedUser()
    return doauth


def MemcacheAuthBackend(server):
    session_cookie = server.config.http.session_cookie
    secret_key = server.config.django.secret_key # change section to django
    def doauth(request):
        sessionid = request.cookies.get(session_cookie)
        if not sessionid:
            raise UnauthenticatedUser()
        session = server.send('memcache', 'get', sessionid).wait()
        if not session:
            # hack to do db read-through. need a better way to configure this behaviour
            rows = server.send('db', "SELECT session_data FROM django_session"
                " WHERE session_key = %s AND expire_date > %s",
                [sessionid, datetime.now()]).wait()
            if rows:
                session = decode(rows[0][0], secret_key)
        if not session or '_auth_user_id' not in session:
            raise UnauthenticatedUser()
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


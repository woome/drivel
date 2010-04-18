from datetime import datetime
from hashlib import sha1
import hmac
TOKEN_DATE_FORMAT = "%Y%m%d%H%M%S"

from drivel.auth import UnauthenticatedUser
from drivel.contrib import username_from_path

def SignedAuthBackend(server):
    from drivel.contrib.django import MemcacheAuthBackend
    from drivel.contrib.django import URLAuthBackend
    mcauth = MemcacheAuthBackend(server)
    urlauth = URLAuthBackend(server)
    secret_key = server.config.django.secret_key
    def doauth(request):
        username = username_from_path(request.path)
        if 'woome-sig' in request.headers:
            sig = request.headers['woome-sig']
            # get username
            h = hmac.new(secret_key, request.body, sha1)
            h.update(username)
            if h.hexdigest() == sig:
                request.environ['woome.signed'] = True
                return urlauth(request)
            else:
                raise UnauthenticatedUser()

        user = mcauth(request)
        if user.username != username:
            raise UnauthenticatedUser()
        return user

    return doauth


def xmpp_credentials(server):
    def get_credentials(user):
        """copied from tokenauth in woome"""
        SECRET_KEY = server.config.django.secret_key
        timestamp = datetime.now()
        timestamp_string = timestamp.strftime(TOKEN_DATE_FORMAT)
        auth_string = "%s:%s:%s:%s" % (SECRET_KEY, user.id,
            user.password, timestamp_string)
        auth_token = "%s:%s:%s" % (timestamp_string, user.id,
            sha1(auth_string).hexdigest())
        return user.username, auth_token
    return get_credentials


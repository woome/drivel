from datetime import datetime
from hashlib import sha1
TOKEN_DATE_FORMAT = "%Y%m%d%H%M%S"

def xmpp_credentials(server):
    def get_credentials(user):
        """copied from tokenauth in woome"""
        SECRET_KEY = server.config.get('woome', 'secret_key')
        timestamp = datetime.now()
        timestamp_string = timestamp.strftime(TOKEN_DATE_FORMAT)
        auth_string = "%s:%s:%s:%s" % (SECRET_KEY, user.id,
            user.password, timestamp_string)
        auth_token = "%s:%s:%s" % (timestamp_string, user.id,
            sha1(auth_string).hexdigest())
        return user.username, auth_token
    return get_credentials


class User(object):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

    def __hash__(self):
        return hash((self.id, self.username))

    def __eq__(self, other):
        return self.username == other.username and \
            self.id == other.id

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return self.username

    def __repr__(self):
        return "<User %s: %s>" % (self.id, self.username)


class UnauthenticatedUser(Exception):
    pass

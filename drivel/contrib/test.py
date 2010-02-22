from drivel.auth import User

def URLAuthBackend(server):
    seen_users = []
    def doauth(request):
        path = request.path.strip('/').split('/')[0]
        if path not in seen_users:
            seen_users.append(path)
        return User(seen_users.index(path), path, '')
    return doauth


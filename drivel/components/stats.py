from drivel.component import WSGIComponent


class PathError(Exception):
    pass


def dpath(dict_, path):
    path = path.strip('/').split('/')
    result = dict_
    try:
        for i in path:
            if isinstance(result, dict):
                result = result[i]  # KeyError
            elif isinstance(result, (tuple, list)):
                i = int(i)  # ValueError
                result = result[i]  # IndexError
            else:
                raise PathError()
    except (KeyError, ValueError, IndexError), e:
        raise PathError()
    return result


class StatsComponent(WSGIComponent):
    subscription = "stats"
    urlmapping = {
        'stats': r'/stats(?P<path>/.+)?/$',
    }

    def __init__(self, server, name):
        super(StatsComponent, self).__init__(server, name)

    def do_stats(self, user, request, proc, path=None):
        stats = self.server.stats()
        if path:
            try:
                stats = dpath(stats, path)
            except KeyError, e:
                # should 404
                return {'error': 'path not found'}
        return stats

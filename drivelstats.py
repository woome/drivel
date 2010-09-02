#!/usr/bin/env python
import optparse
import urlparse

import httplib2
import simplejson

join = lambda *args: '/'.join(args)

safestr = lambda obj: obj if isinstance(obj, basestring) else str(obj)


def dataunfold(root, data):
    if isinstance(data, dict):
        for k, v in data.iteritems():
            for i, j in dataunfold(join(root, k), v):
                yield i, j
    elif isinstance(data, (tuple, list)):
        yield root, ','.join(safestr(i) for i in data)
    else:
        yield root, safestr(data)


def drivelstats(url):
    httpclient = httplib2.Http()
    try:
        head, resp = httpclient.request(url, 'GET')
        assert head.status == 200
        data = simplejson.loads(resp)
    except Exception, e:
        print 'ERROR %s: %s' % (url, e)
    else:
        url = urlparse.urlparse(url)
        for k, v in dataunfold(url.path.strip('/'), data):
            print '%s: %s' % (k, v)

if __name__ == '__main__':
    parser = optparse.OptionParser()
    option, args = parser.parse_args()
    if len(args) == 0:
        parser.error('please specify a url')
    drivelstats(args[0])

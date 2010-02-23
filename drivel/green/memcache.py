from eventlet import patcher
patcher.inject('memcache',
    globals())

del patcher


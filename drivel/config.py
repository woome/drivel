from __future__ import with_statement
import ConfigParser


def dotted_import(name):
    mod, attr = name.split('.'), []
    obj = None
    while mod:
        try:
            obj = __import__('.'.join(mod), {}, {}, [''])
        except ImportError, e:
            attr.insert(0, mod.pop())
        else:
            for a in attr:
                try:
                    obj = getattr(obj, a)
                except AttributeError, e:
                    raise AttributeError('could not get attribute %s from %s'
                        ' -> %s (%r)' % (a, '.'.join(mod), '.'.join(attr),
                        obj))
            return obj
    raise ImportError('could not import %s' % name)


class Config(dict):
    """Better Config Container.

    subclass of dict.
    takes a RawConfigParser instance to constructor too.

    """
    def __init__(self, config):
        if isinstance(config, ConfigParser.RawConfigParser):
            for section in config.sections():
                self[section] = Config(dict(config.items(section)))
        else:
            for key, val in config.iteritems():
                self[key] = Config(val) if isinstance(val, dict) else val

    def import_(self, key):
        return dotted_import(self[key])

    def get(self, key, default=None):
        if isinstance(key, tuple):
            try:
                return self[key]
            except KeyError, e:
                return default
        else:
            return super(Config, self).get(key, default)

    def getint(self, key, default=None, return_none=False):
        val = self.get(key, default)
        if val is None and return_none:
            return val
        return int(val)

    def getfloat(self, key, default=None, return_none=False):
        val = self.get(key, default)
        if val is None and return_none:
            return val
        return float(val)

    def getboolean(self, key, default=None, return_none=True):
        val = self.get(key, default)
        if val is None and return_none:
            return None
        if isinstance(val, basestring):
            val = val.lower()
            if val in ['1', 'yes', 'true', 'on']:
                return True
            elif val in ['0', 'no', 'false', 'off']:
                return False
        elif isinstance(val, bool):
            return val
        else:
            raise ValueError()

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError, e:
            return self.__getattribute__(key)

    def __getitem__(self, key):
        if isinstance(key, tuple):
            val = self
            for k in key:
                val = val[k]
            return val
        else:
            return dict.__getitem__(self, key)

    def __contains__(self, key):
        if isinstance(key, tuple):
            val = self
            for k in key:
                if k not in val:
                    return False
                val = val[k]
            return True
        else:
            return dict.__contains__(self, key)


def fromfile(file):
    config = ConfigParser.RawConfigParser()
    if isinstance(file, basestring):
        with open(file) as f:
            config.readfp(f)
    else:
        config.readfp(file)
    return Config(config)

# END

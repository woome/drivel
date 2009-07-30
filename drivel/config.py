from __future__ import with_statement
import ConfigParser

from eventlet import api

class Config(dict):
    def __init__(self, config):
        if isinstance(config, ConfigParser.RawConfigParser):
            for section in config.sections():
                self[section] = Config(dict(config.items(section)))
        else:
            super(Config, self).__init__(config)
            
    def import_(self, key):
        return api.named(self[key])

    def get(self, key, default=None):
        if isinstance(key, tuple):
            try:
                return self[key]
            except KeyError, e:
                return default
        else:
            return super(Config, self).get(key, default)

    def getint(self, key, default=None):
        return int(self.get(key, default))

    def getfloat(self, key, default=None):
        return float(self.get(key, default))

    def getboolean(self, key, default=None):
        val = self.get(key, default)
        if not val:
            return None
        val = val.lower()
        if val in ['1', 'yes', 'true', 'on']:
            return True
        elif val in ['0', 'no', 'false', 'off']:
            return False
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


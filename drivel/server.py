from __future__ import with_statement
from collections import defaultdict
import logging
import re
import sys

import eventlet
from eventlet import backdoor
from eventlet import event
from eventlet import hubs
from eventlet import queue
from eventlet import wsgi

from drivel.config import fromfile as config_fromfile
from drivel.wsgi import create_application

class Server(object):
    def __init__(self, config):
        self.config = config
        self.components = {}
        self._mqueue = queue.Queue()
        self.subscriptions = defaultdict(list)
        self.wsgiroutes = []
        #concurrency = 4
        #if self.config.has_option('server', 'mq_concurrency'):
            #concurrency = self.config.getint('server', 'mq_concurrency')
        #self._pool = pool.Pool(max_size=concurrency)
        self._setupLogging()

    def start(self, start_listeners=True):
        self.log('Server', 'info', 'starting server')
        for name in self.config.components:
            self.components[name] = self.config.components.import_(name)(self, name)
        self._greenlet = eventlet.spawn_n(self._process)
        if start_listeners and 'backdoor_port' in self.config.server:
            # enable backdoor console
            bdport = self.config.getint(('server', 'backdoor_port'))
            self.log('Server', 'info', 'enabling backdoor on port %s'
                % bdport)
            eventlet.spawn_n(backdoor.backdoor_server,
                eventlet.listen(('127.0.0.1', bdport)),
                locals={'server': self})
        app = create_application(self)
        self.wsgiapp = app
        if start_listeners:
            numsimulreq = self.config.get(('http', 'max_simultaneous_reqs'))
            host = self.config.http.address
            port = self.config.http.getint('port')
            sock = eventlet.listen((host, port))
            pool = self.server_pool = eventlet.GreenPool(10000)
            wsgi.server(sock, app, custom_pool=pool)

    def stop(self):
        for name, mod in self.components.items():
            mod.stop()
            del self.components[name]
        if not self._greenlet.dead:
            self._greenlet.throw()

    def _process(self):
        """process message queue"""
        while True:
            event, subscription, message = self._mqueue.get()
            if subscription in self.subscriptions and len(
                self.subscriptions[subscription]):
                self.log('Server', 'debug', 'processing message '
                    'for %s: %s' % (subscription, message))
                for subscriber in self.subscriptions[subscription]:
                    subscriber.put((event, message))
            elif event:
                self.log('Server', 'warning', "couldn't find "
                    "subscribers for %s: %s" % (subscription, message))
                #event.send_exception()

    def send(self, subscription, *message):
        self.log('Server', 'debug', 'receiving message for %s'
            ': %s' % (subscription, message))
        evt = event.Event()
        self._mqueue.put((evt, subscription, message))
        return evt

    def subscribe(self, subscription, queue):
        self.log('Server', 'info', 'adding subscription to %s'
            % subscription)
        self.subscriptions[subscription].append(queue)

    def add_wsgimapping(self, mapping, subscription):
        if not isinstance(mapping, (tuple, list)):
            mapping = (None, mapping)

        mapping = (subscription, mapping[0], re.compile(mapping[1]))
        self.wsgiroutes.append(mapping)

    def log(self, logger, level, message):
        logger = logging.getLogger(logger)
        getattr(logger, level)(message)

    def _setupLogging(self):
        level = getattr(logging,
            self.config.server.log_level.upper())
        logging.basicConfig(level=level, stream=sys.stdout)

    def stats(self):
        stats = dict((key, comp.stats()) for key, comp
            in self.components.items())
        stats.update({
            'server': {
                'items': len(self._mqueue),
            }
        })
        return stats


def start(config, options):
    if 'hub_module' in config.server:
        hubs.use_hub(config.server.import_('hub_module'))
    from eventlet import patcher
    patcher.monkey_patch(all=False, socket=True, select=True, os=True)
    server = Server(config)
    server.start()

def main():
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-c', '--config', dest='config',
        help="configuration file")
    options, args = parser.parse_args()
    if not options.config:
        parser.error('please specify a config file')
    conf = config_fromfile(options.config)
    start(conf, options)

if __name__ == '__main__':
    main()


from collections import defaultdict
import logging
import sys

from eventlet import api
from eventlet import coros
from eventlet import pool
from eventlet import wsgi

from .wsgi import create_application

class Server(object):
    def __init__(self, config):
        self.config = config
        self.components = {}
        self._mqueue = coros.queue()
        self.subscriptions = defaultdict(list)
        #concurrency = 4
        #if self.config.has_option('server', 'mq_concurrency'):
            #concurrency = self.config.getint('server', 'mq_concurrency')
        #self._pool = pool.Pool(max_size=concurrency)
        self._setupLogging()

    def start(self):
        self.log('Server', 'info', 'starting server')
        for name, mod in self.config.items('components'):
            self.components[name] = api.named(mod)(self)
        self._greenlet = api.spawn(self._process)
        app = create_application(self)
        host = self.config.get('http', 'address')
        port = self.config.getint('http', 'port')
        sock = api.tcp_listener((host, port))
        wsgi.server(sock, app)

    def stop(self):
        for name, mod in self.components.items():
            mod.stop()
            del self.components[name]
        if not self._greenlet.dead:
            self._greenlet.throw()

    def _process(self):
        """process message queue"""
        while True:
            event, subscription, message = self._mqueue.wait()
            if subscription in self.subscriptions and len(
                self.subscriptions[subscription]):
                self.log('Server', 'debug', 'processing message '
                    'for %s: %s' % (subscription, message))
                for subscriber in self.subscriptions[subscription]:
                    subscriber.send((event, message))
            elif event:
                self.log('Server', 'warning', "couldn't find "
                    "subscribers for %s: %s" % (subscription, message))
                #event.send_exception()
    def send(self, subscription, *message):
        self.log('Server', 'debug', 'receiving message for %s'
            ': %s' % (subscription, message))
        event = coros.event()
        self._mqueue.send((event, subscription, message))
        return event

    def subscribe(self, subscription, queue):
        self.log('Server', 'info', 'adding subscription to %s'
            % subscription)
        self.subscriptions[subscription].append(queue)

    def log(self, logger, level, message):
        logger = logging.getLogger(logger)
        getattr(logger, level)(message)

    def _setupLogging(self):
        level = getattr(logging,
            self.config.get('server', 'log_level').upper())
        logging.basicConfig(level=level, stream=sys.stdout)


def start(config, options):
    from eventlet import util
    util.wrap_socket_with_coroutine_socket()
    util.wrap_select_with_coroutine_select()
    util.wrap_pipes_with_coroutine_pipes()
    server = Server(config)
    server.start()

def main():
    from ConfigParser import RawConfigParser
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-c', '--config', dest='config',
        help="configuration file")
    options, args = parser.parse_args()
    if not options.config:
        parser.error('please specify a config file')
    config = RawConfigParser()
    with open(options.config) as f:
        config.readfp(f)
    start(config, options)

if __name__ == '__main__':
    main()


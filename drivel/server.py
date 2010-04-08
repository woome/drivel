from __future__ import with_statement
from collections import defaultdict
import gc
import logging
import pprint
import re
import signal
import sys
import time

import eventlet
from eventlet import backdoor
from eventlet import event
from eventlet import hubs
from eventlet import queue
from eventlet import wsgi

from drivel.config import fromfile as config_fromfile
from drivel.utils import debug
from drivel.wsgi import create_application

def statdumper(server, interval):
    while True:
        pprint.pprint(server.stats())
        eventlet.sleep(interval)

def timed_switch_out(self):
    self._last_switch_out = time.time()

from eventlet.greenthread import GreenThread
GreenThread.switch_out = timed_switch_out

class safe_exit(object):
    exit_advice = 'exit from telnet is ^]'
    def __call__(self):
        print self.exit_advice

    def __repr__(self):
        return self.exit_advice

    def __str__(self):
        return self.exit_advice


class dummylog(object):
    def write(self, data):
        pass


class Server(object):
    def __init__(self, config, options):
        self.config = config
        self.options = options
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
        self._greenlet = eventlet.spawn(self._process)
        if start_listeners and 'backdoor_port' in self.config.server:
            # enable backdoor console
            bdport = self.config.getint(('server', 'backdoor_port'))
            self.log('Server', 'info', 'enabling backdoor on port %s'
                % bdport)
            eventlet.spawn(backdoor.backdoor_server,
                eventlet.listen(('127.0.0.1', bdport)),
                locals={'server': self,
                        'debug': debug,
                        'exit': safe_exit(),
                        'quit': safe_exit(),
                        'stats': lambda: pprint.pprint(self.stats()),
                })
        app = create_application(self)
        self.wsgiapp = app
        if start_listeners:
            numsimulreq = self.config.get(('http', 'max_simultaneous_reqs'))
            host = self.config.http.address
            port = self.config.http.getint('port')
            sock = eventlet.listen((host, port))
            pool = self.server_pool = eventlet.GreenPool(10000)
            log = (self.options.nohttp or self.options.statdump) and \
                dummylog() or None
            wsgi.server(sock, app, custom_pool=pool, log=log)

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

    def stats(self, gc_collect=False):
        stats = dict((key, comp.stats()) for key, comp
            in self.components.items())
        hub = hubs.get_hub()
        gettypes = lambda t: [o for o in gc.get_objects() if 
            type(o).__name__ == t]
        if gc_collect:
            gc.collect() and gc.collect()
        stats.update({
            'server': {
                'items': self._mqueue.qsize(),
                'wsgi_free': self.server_pool.free(),
                'wsgi_running': self.server_pool.running(),
            },
            'eventlet': {
                'next_timers': len(hub.next_timers),
                'timers': len(hub.timers),
                'readers': len(hub.listeners['read']),
                'writers': len(hub.listeners['write']),
                'timers_count': hub.get_timers_count(),
            },
            'python': {
                'greenthreads': len(gettypes('GreenThread')),
                'gc_tracked_objs': len(gc.get_objects()),
            }
        })
        return stats


def start(config, options):
    if 'hub_module' in config.server:
        hubs.use_hub(config.server.import_('hub_module'))
    from eventlet import patcher
    patcher.monkey_patch(all=False, socket=True, select=True, os=True)
    server = Server(config, options)

    #def drop_to_shell(s, f):
        #from IPython.Shell import IPShell
        #s = IPShell([], {'server': server,
                         #'debug': debug,
                         #'stats': lambda: pprint.pprint(server.stats()),
                        #})
        #s.mainloop()
    #signal.signal(signal.SIGUSR2, drop_to_shell)

    if options.statdump:
        interval = options.statdump
        eventlet.spawn_after(interval, statdumper, server, interval)
    server.start()


# Some lifecycle methods for standard unix server stuff
import daemon
import os

def lifecycle_cleanup():
    """Terminate the process nicely."""
    sys.exit(0)

def lifecycle_start(conf, options):
    with daemon.DaemonContext() as dctx:
        # Write the pid
        with open(conf.server.get(
                "pidfile", 
                "/tmp/drivel.pid"
                ), "w") as pidfile:
            pidfile.write("%s\n" % os.getpid())

        # Set the signal map
        dctx.signal_map = {
            signal.SIGTERM: lifecycle_cleanup,
            }
        start(conf, options)

def lifecycle_stop(conf, options):
    with open(conf.server.get("pidfile", "/tmp/drivel.pid")) as pidfile:
        pid = pidfile.read()
        try:
            os.kill(int(pid), signal.SIGTERM)
        except Exception, e:
            print >>sys.stderr, "couldn't stop %s" % pid
    

def main():
    from optparse import OptionParser
    usage = "%prog [options] [start|stop|help]"
    parser = OptionParser(usage=usage)
    parser.add_option('-c', '--config', dest='config',
        help="configuration file")
    parser.add_option('-s', '--statdump', dest='statdump',
        metavar='INTERVAL', type="int",
        help="dump stats at INTERVAL seconds")
    parser.add_option('-n', '--no-http-logs', dest='nohttp',
        action="store_true",
        help="disable logging of http requests from wsgi server")
    parser.add_option(
        '-D', 
        '--no-daemon', 
        dest='nodaemon',
        action="store_true",
        help="disable daemonification if specified in config"
        )
    options, args = parser.parse_args()
    if not options.config:
        parser.error('please specify a config file')
    conf = config_fromfile(options.config)

    if "start" in args:
        if conf.server.daemon and not(options.nodaemon):
            lifecycle_start(conf, options)
        else:
            start(conf, options)

    elif "stop" in args:
        lifecycle_stop(conf, options)

    elif "help" in args:
        parser.print_help()

if __name__ == '__main__':
    main()


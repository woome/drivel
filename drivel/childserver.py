from collections import defaultdict
import logging
import socket
import sys
import uuid

from carrot.connection import BrokerConnection
from carrot.messaging import Consumer
from carrot.messaging import Publisher
from eventlet import coros
from eventlet import greenio
from eventlet import proc
from eventlet import wsgi

from drivel.event import remoteevent
from drivel.event import EventManager
from drivel.wsgi import create_application

class ChildServer(object):
    def __init__(self, config, httpsockfd, id=None):
        self.config = config
        _sock = socket.fromfd(httpsockfd, socket.AF_INET, socket.SOCK_STREAM)
        self.httpsock = greenio.GreenSocket(_sock)
        self.id = id or uuid.uuid4().hex
        self.broker = self.create_broker()
        self.publisher = Publisher(
            connection=self.broker,
            exchange='messaging',
            exchange_type='topic'
        )
        self.mqueue = coros.queue()
        self.eventmanager = EventManager(self.id,
            Publisher(
                connection=self.broker,
                exchange='return',
                exchange_type='topic',
                durable=False,
                auto_delete=True,
        ))
        self.procs = proc.RunningProcSet()
        self.components = {}
        self.subscriptions = defaultdict(list)
        self._setup_logging()

    def create_broker(self):
        brconf = self.config.broker
        return BrokerConnection(
            hostname=brconf.host,
            port=brconf.getint('port'),
            userid=brconf.get('username', None),
            password=brconf.get('password', None),
            virtual_host=brconf.get('vhost', None),
            ssl=brconf.getboolean('ssl', False),
            backend_cls=brconf.get('backend_class', None)
        )

    def _wait(self, consumer, callback):
        with consumer:
            consumer.register_callback(callback)
            for msg in consumer.iterconsume():
                pass

    def _serve_http(self):
        app = create_application(self)
        self.wsgiapp = app
        wsgi.server(self.httpsock, app)

    def _incoming_message(self, payload, msg):
        print 'got message', payload
        subscriber = payload['envelopeto']
        returnid = payload['returnid']
        event = self.eventmanager.getreturner(returnid)
        if subscriber in self.subscriptions:
            for sub in self.subscriptions[subscriber]:
                sub.send((event, payload['data']))
        msg.ack()

    def _incoming_return(self, payload, msg):
        print 'got return', payload
        returnid = payload['envelopeto']
        self.eventmanager.return_(returnid, payload['data'])
        msg.ack()

    def _process_outqueue(self):
        while True:
            to, event, message = self.mqueue.get()
            try:
                self._do_send(to, event, message)
            except Exception,e:
                event.send_exception(e)

    def start(self):
        for name in self.config.components:
            self.components[name] = self.config.components.import_(name)(self)
        self.procs.spawn(self._process_outqueue)
        self.procs.spawn(self._serve_http)
        consumer = Consumer(connection=self.broker,
            exchange='messaging',
            exchange_type='topic',
            queue='messaging',
            routing_key='*'
        )
        self.procs.spawn(self._wait, consumer, self._incoming_message)
        consumer = Consumer(connection=self.broker,
            exchange='return',
            exchange_type='topic',
            queue='return:%s' % self.id,
            routing_key='%s.*' % self.id,
            durable=False,
            auto_delete=True
        )
        self.procs.spawn(self._wait, consumer, self._incoming_return)

    def wait(self):
        self.procs.waitall()

    def send(self, to, *message):
        event, eventid = self.eventmanager.create()
        self.mqueue.put((to, event, message))
        return event

    def _do_send(self, to, event, message):
        self.publisher.send({
                'processid': self.id,
                'returnid': event.id,
                'envelopeto': to,
                'data': message
            },
            routing_key=to,
            mandatory=True,
            serializer='pickle'
        )

    # from original code...

    def subscribe(self, subscription, queue):
        self.log('Server', 'info', 'adding subscription to %s'
            % subscription)
        self.subscriptions[subscription].append(queue)

    def log(self, logger, level, message):
        logger = logging.getLogger(logger)
        getattr(logger, level)(message)

    def _setup_logging(self):
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



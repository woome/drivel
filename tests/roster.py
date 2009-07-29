from unittest import TestCase

from eventlet import coros
from mock import Mock

from drivel.auth import User
from drivel.components.roster import RosterManager

def send(queue, *message):
    # synchronous message send
    event = coros.event()
    queue.send((event, message))
    event.wait()


class RosterTestCase(TestCase):
    def setUp(self):
        server = Mock(spec=['send', 'subscribe', 'log'])
        RosterManager.asynchronous = False
        manager = RosterManager(server)
        assert server.subscribe.called
        (subscription, queue), _kwargs = server.subscribe.call_args 
        assert subscription == 'roster'
        self.server = server
        self.manager = manager
        self.queue = queue

    def test_simple(self):
        # send a simple presence and check the data sent to cache
        server, manager, queue = self.server, self.manager, self.queue
        send(queue, 'presence', "<presence"
            " from='romeo@example.net/orchard'"
            " to='juliet@example.com'/>")
        # check data sent to memcache
        assert server.send.called and server.send.call_count == 1
        args = server.send.call_args[0]
        assert args[0:3] == ('memcache', 'set', 'buddylist:juliet'), args[0:3]
        roster = args[3]
        assert roster['romeo']['status'] == 'available'
        assert 'orchard' in roster['romeo']['resources']

    def test_resource_tracking(self):
        server, manager, queue = self.server, self.manager, self.queue
        send(queue, 'presence', "<presence"
            " from='romeo@example.net/orchard'"
            " to='juliet@example.com'/>")

        send(queue, 'presence', "<presence"
            " from='romeo@example.net/chamber'"
            " to='juliet@example.com'/>")

        args, kwargs = server.send.call_args
        assert set(['orchard', 'chamber']) == set(args[3]['romeo']['resources'])

        send(queue, 'presence', "<presence"
            " from='romeo@example.net/chamber'"
            " to='juliet@example.com'"
            " type='unavailable'/>")

        # get last call to send
        roster = server.send.call_args[0][3]
        assert roster['romeo']['status'] == 'available'
        assert 'orchard' in roster['romeo']['resources']
        assert 'chamber' not in roster['romeo']['resources']

        send(queue, 'presence', "<presence"
            " from='romeo@example.net/orchard'"
            " to='juliet@example.com'"
            " type='unavailable'/>")

        # get last call to send
        roster = server.send.call_args[0][3]
        assert roster['romeo']['status'] == 'unavailable'
        assert 'orchard' not in roster['romeo']['resources']

    def test_connection_termination(self):
        server, manager, queue = self.server, self.manager, self.queue
        send(queue, 'presence', "<presence"
            " from='romeo@example.net/orchard'"
            " to='juliet@example.com'/>")
        # assert we have a roster
        assert 'juliet' in manager.accounts
        # now terminate the connection
        send(queue, 'conn-termination', User(0, 'juliet', ''))
        # and check the non-existence of a roster
        assert 'juliet' not in manager.accounts
        # and deleted from memcache
        assert server.send.call_args[0] == ('memcache', 'del',
            'buddylist:juliet')



#END


from unittest import TestCase

from mock import Mock

from drivel import event

event.coros.event = Mock(spec=event.coros.event)
event.coros.semaphore = Mock(spec=event.coros.semaphore)

class EventManagerTestCase(TestCase):
    def setUp(self):
        self.publisher = Mock()
        self.evt = event.EventManager(self.publisher)

    def test_return(self):
        event, id = self.evt.create()
        msg = 'test message'
        self.evt.return_(id, {'result': msg})
        assert event.send.called
        assert event.send.call_args[1]['result'] == msg
        assert not event.send.call_args[1]['exc']

    def test_returner(self):
        event, id = self.evt.create()
        returnevent = self.evt.getreturner(id)
        msg = 'test message'
        returnevent.send(msg)
        assert self.evt.publisher.send.called
        datasent = self.publisher.send.call_args[0][0]
        assert datasent['envelopeto'] == id
        assert datasent['data']['result'] == msg
        assert not datasent['data']['exc']


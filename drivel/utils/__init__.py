from eventlet import sleep
from eventlet import debug
from eventlet.event import Event

class RemovedException(Exception):
    pass

class DLItem(object):
    def __init__(self, val):
        self.val = val
        self._prev = None
        self._next = None
        self.removed = False

    def next(self):
        print 'NEXT', self.val, self._next
        return self._next

    def set_next(self, next):
        print 'SET_NEXT', self.val, next
        self._next = next

    def prev(self):
        print 'PREV', self.val, self._prev
        return self._prev

    def set_prev(self, prev):
        print 'SET_PREV', self.val, prev
        self._prev = prev

    def remove(self):
        if not self.removed:
            print 'REM', self.val
            if self._prev:
                self._prev.set_next(self._next)
            if self._next:
                self._next.set_prev(self._prev)
            self.removed = True

    def __repr__(self):
        return repr(self.val)

    def __str__(self):
        return str(self.val)


class LinkedList(object):
    def __init__(self):
        self.head = self.tail = DLItem(None)
        self._event = event = Event()
        self.wait = event.wait

    def append(self, val):
        item = DLItem(val)
        item.set_prev(self.tail)
        self.tail.set_next(item)
        self.tail = item
        self._event.send(True)
        self._event.reset()
        return item


    def get(self, matchfunc=lambda i: True):
        item = self.head
        while True:
            while True:
                print '--getting next'
                next = item.next()
                print '--next', next
                if not next:
                    print '--no items, waiting'
                    self.wait()
                    print '--awoken'
                else:
                    item = next
                    break

            if not item.removed and matchfunc(item):
                item.remove()
                print '--returning', item.val
                user,proc = item.val
                proc.greenlet.throw()
                return user
            else:
                print '--discarded', item.val[0]

            sleep(0)  # yield


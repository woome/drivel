import collections
import time

import eventlet


class LRU(object):
    def __init__(self):
        self.lru_coll = collections.deque()
        self.val_count = {}

    def add(self, value):
        t = time.time()
        self.lru_coll.append((t, value))
        self.val_count[value] = self.val_count.get(value, 0) + 1

    def stats(self):
        return {'unique_items': len(self.val_count),
                'lru_length': len(self.lru_coll), }

    def remove_val(self, value):
        self.val_count[value] -= 1
        if self.val_count[value] == 0:
            del self.val_count[value]
            return True
        return False

    def remove_by_age(self, maxage, yield_every=None):  # maxage is secs
        unyielded_count = 0
        while self.lru_coll and self.lru_coll[0][0] + maxage < time.time():
            addtime, value = self.lru_coll.popleft()
            if self.remove_val(value):
                yield value
            unyielded_count += 1
            if yield_every and unyielded_count >= yield_every:
                eventlet.sleep(0)
                unyielded_count = 0

    def remove(self, count, yield_every=None):
        unyielded_count = 0
        num_removed = 0
        while self.lru_coll and num_removed < count:
            addtime, value = self.lru_coll.popleft()
            if self.remove_val(value):
                yield value
            unyielded_count += 1
            if yield_every and unyielded_count >= yield_every:
                eventlet.sleep(0)
                unyielded_count = 0

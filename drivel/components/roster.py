from datetime import datetime
# third-party imports
import xmpp
# local imports
from drivel.component import Component

presencemapping = {
        'username_from': lambda p: p.getFrom().node,
        'resource_from': lambda p: p.getFrom().resource,
        'username_to': lambda p: p.getTo().node,
        'type': lambda p: p.getType(),
        'show': lambda p: p.getShow(),
        'priority': lambda p: p.getPriority(),
        'status': lambda p: p.getStatus(),
        'extension': lambda p: (lambda e: e and
            e.getAttr('type'))(p.getTag('extension')),
    }


class UnhandleablePresence(Exception):
    pass


class Presence(object):
    def __init__(self, xml):
        _pnode = xmpp.simplexml.XML2Node(xml)
        _presence = xmpp.protocol.Presence(node=_pnode)
        for key, func in presencemapping.iteritems():
            setattr(self, key, func(_presence))


class RosterManager(Component):
    subscription = 'roster'

    def __init__(self, server, name):
        super(RosterManager, self).__init__(server, name)
        self.accounts = {}
        self._numpresences = 0

    def _presence_logic(self, contact, presence):
        ptype = presence.type
        resource = presence.resource_from
        if ptype == 'unavailable':
            if presence.extension == 'canonicalunavailable':
                contact['resources'].clear()
                contact['status'] = ptype
            else:
                try:
                    del contact['resources'][resource]
                except KeyError, e:
                    pass
                if not contact['resources']:
                    contact['status'] = ptype
        elif not ptype:
            show = presence.show or 'available'
            extension = presence.extension
            date = datetime.now()
            contact['resources'][resource] = (show, extension, date)
            contact['status'] = show + ('+%s' % extension if extension else '')
            contact['lastseen'] = date
        else:
            raise UnhandleablePresence('unknown presence type')
        return contact

    def handle_presence(self, presencexml):
        presence = Presence(presencexml)
        user = presence.username_to

        roster = self.accounts.setdefault(user, {})
        contact = roster.setdefault(presence.username_from, {
            'status': 'unavailable',
            'lastseen': datetime.now(),
            'resources': {},
        })
        try:
            self._presence_logic(contact, presence)
            key = ('buddylist:%s' % user).encode('ascii')
            self.server.send('memcache', 'set', key, roster)
        except UnhandleablePresence, e:
            pass

    def handle_message(self, message):
        method = message[0]
        if method == 'presence':
            presence = message[1]
            self.handle_presence(presence)
            self._numpresences += 1
        elif method == 'conn-termination':
            user = message[1].username
            try:
                del self.accounts[user]
                self.server.send('memcache', 'del', 'buddylist:%s' % user)
            except KeyError, e:
                pass

    def stats(self):
        stats = super(RosterManager, self).stats()
        stats.update({
            'roster:rostersmanaged': len(self.accounts),
            'roster:presenceshandled': self._numpresences,
        })
        return stats

#END


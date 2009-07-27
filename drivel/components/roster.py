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
            setattr(self, key, func(_presence)


class Contact(object):
    def __init__(self, user):
        self.user = user
        self.presence = 'unavailable'
        self.lastseen = datetime.now()
        self.resources = {}

    def handle_presence(self, presence):
        ptype = presence.type
        resource = presence.resource_from
        if ptype == 'unavailable':
            if presence.extension == 'canonicalunavailable':
                self.resources.clear()
                self.presence = 'unavailable'
            else:
                try:
                    del self.resources[resource]
                    if not self.resources[resource]:
                        self.presence = 'unavailable'
                except KeyError, e:
                    pass
        else if not ptype:
            show = presence.show
            extension = presence.extension
            date = datetime.now()
            self.resources[resource] = (show, extension, date)
            self.presence = show + ('+%s' % extension if extension else '')
            self.lastseen = date
        else:
            raise UnhandleablePresence('unknown presence type')


class Roster(object):
    def __init__(self):
        self.contacts = {}

    def handle_presence(self, presence):
        user = presence.username_from
        try:
            contact = self.contacts[user]
        except KeyError, e:
            contact = Contact(user)

        contact.handle_presence(presence)


class RosterManager(Component):
    subscription = 'roster'

    def __init__(self, server):
        super(RosterManager, self).__init__(server)
        self.accounts = {}
        self._numpresences = 0

    def handle_presence(self, presencexml):
        presence = Presence(presencexml)
        user = presence.username_from
        try:
            roster = self.accounts[user]
        except KeyError, e:
            roster = Roster()
            self.accounts[user] = roster

        try:
            roster.handle_presence(presence)
            self.write_to_cache(user, roster)
        except UnhandleablePresence, e:
            pass

    def _handle_message(self, event, message):
        method = message[0]
        if method == 'presence':
            presence = message[1]
            self.handle_presence(presence)
            self._numpresences += 1
        elif method == 'conn-termination':
            user = message[1]
        event.send()

    def write_to_cache(self, user, roster):
        pass

    def stats(self):
        stats = super(RosterManager, self).stats()
        stats.update({
            'roster:rostersmanaged': len(self.accounts),
            'roster:presenceshandled': self._numpresences,
        })
        return stats

#END


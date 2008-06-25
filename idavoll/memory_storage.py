# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

import copy
from zope.interface import implements
from twisted.internet import defer
from twisted.words.protocols.jabber import jid

from idavoll import error, iidavoll

defaultConfig = {"pubsub#persist_items": True,
                  "pubsub#deliver_payloads": True,
                  "pubsub#send_last_published_item": 'on_sub',
                  "pubsub#node_type": "leaf"}

class Storage:

    implements(iidavoll.IStorage)

    def __init__(self):
        self._nodes = {}


    def getNode(self, nodeIdentifier):
        try:
            node = self._nodes[nodeIdentifier]
        except KeyError:
            return defer.fail(error.NodeNotFound())

        return defer.succeed(node)


    def getNodeIds(self):
        return defer.succeed(self._nodes.keys())


    def createNode(self, nodeIdentifier, owner, config=None):
        if nodeIdentifier in self._nodes:
            return defer.fail(error.NodeExists())

        if not config:
            config = copy.copy(defaultConfig)

        if config['pubsub#node_type'] != 'leaf':
            raise NotImplementedError

        node = LeafNode(nodeIdentifier, owner, config)
        self._nodes[nodeIdentifier] = node

        return defer.succeed(None)


    def deleteNode(self, nodeIdentifier):
        try:
            del self._nodes[nodeIdentifier]
        except KeyError:
            return defer.fail(error.NodeNotFound())

        return defer.succeed(None)


    def getAffiliations(self, entity):
        entity = entity.userhost()
        return defer.succeed([(node.nodeIdentifier, node._affiliations[entity])
                              for name, node in self._nodes.iteritems()
                              if entity in node._affiliations])


    def getSubscriptions(self, entity):
        subscriptions = []
        for node in self._nodes.itervalues():
            for subscriber, subscription in node._subscriptions.iteritems():
                subscriber = jid.internJID(subscriber)
                if subscriber.userhostJID() == entity.userhostJID():
                    subscriptions.append((node.nodeIdentifier, subscriber,
                                          subscription.state))

        return defer.succeed(subscriptions)



class Node:

    implements(iidavoll.INode)

    def __init__(self, nodeIdentifier, owner, config):
        self.nodeIdentifier = nodeIdentifier
        self._affiliations = {owner.userhost(): 'owner'}
        self._subscriptions = {}
        self._config = config


    def getType(self):
        return self.nodeType


    def getConfiguration(self):
        return self._config


    def getMetaData(self):
        config = copy.copy(self._config)
        config["pubsub#node_type"] = self.nodeType
        return config


    def setConfiguration(self, options):
        for option in options:
            if option in self._config:
                self._config[option] = options[option]

        return defer.succeed(None)


    def getAffiliation(self, entity):
        return defer.succeed(self._affiliations.get(entity.full()))


    def getSubscription(self, subscriber):
        try:
            subscription = self._subscriptions[subscriber.full()]
        except KeyError:
            state = None
        else:
            state = subscription.state
        return defer.succeed(state)


    def addSubscription(self, subscriber, state):
        if self._subscriptions.get(subscriber.full()):
            return defer.fail(error.SubscriptionExists())

        subscription = Subscription(state)
        self._subscriptions[subscriber.full()] = subscription
        return defer.succeed(None)


    def removeSubscription(self, subscriber):
        try:
            del self._subscriptions[subscriber.full()]
        except KeyError:
            return defer.fail(error.NotSubscribed())

        return defer.succeed(None)


    def getSubscribers(self):
        subscribers = [jid.internJID(subscriber) for subscriber, subscription
                       in self._subscriptions.iteritems()
                       if subscription.state == 'subscribed']

        return defer.succeed(subscribers)


    def isSubscribed(self, entity):
        for subscriber, subscription in self._subscriptions.iteritems():
            if jid.internJID(subscriber).userhost() == entity.userhost() and \
                    subscription.state == 'subscribed':
                return defer.succeed(True)

        return defer.succeed(False)


    def getAffiliations(self):
        affiliations = [(jid.internJID(entity), affiliation) for entity, affiliation
                       in self._affiliations.iteritems()]

        return defer.succeed(affiliations)



class PublishedItem(object):
    """
    A published item.

    This represent an item as it was published by an entity.

    @ivar element: The DOM representation of the item that was published.
    @type element: L{Element<twisted.words.xish.domish.Element>}
    @ivar publisher: The entity that published the item.
    @type publisher: L{JID<twisted.words.protocols.jabber.jid.JID>}
    """

    def __init__(self, element, publisher):
        self.element = element
        self.publisher = publisher



class LeafNodeMixin:

    nodeType = 'leaf'

    def __init__(self):
        self._items = {}
        self._itemlist = []


    def storeItems(self, items, publisher):
        for element in items:
            item = PublishedItem(element, publisher)
            itemIdentifier = element["id"]
            if itemIdentifier in self._items:
                self._itemlist.remove(self._items[itemIdentifier])
            self._items[itemIdentifier] = item
            self._itemlist.append(item)

        return defer.succeed(None)


    def removeItems(self, itemIdentifiers):
        deleted = []

        for itemIdentifier in itemIdentifiers:
            try:
                item = self._items[itemIdentifier]
            except KeyError:
                pass
            else:
                self._itemlist.remove(item)
                del self._items[itemIdentifier]
                deleted.append(itemIdentifier)

        return defer.succeed(deleted)


    def getItems(self, maxItems=None):
        if maxItems:
            itemList = self._itemlist[-maxItems:]
        else:
            itemList = self._itemlist
        return defer.succeed([item.element for item in itemList])


    def getItemsById(self, itemIdentifiers):
        items = []
        for itemIdentifier in itemIdentifiers:
            try:
                item = self._items[itemIdentifier]
            except KeyError:
                pass
            else:
                items.append(item.element)
        return defer.succeed(items)


    def purge(self):
        self._items = {}
        self._itemlist = []

        return defer.succeed(None)



class LeafNode(Node, LeafNodeMixin):

    implements(iidavoll.ILeafNode)

    def __init__(self, nodeIdentifier, owner, config):
        Node.__init__(self, nodeIdentifier, owner, config)
        LeafNodeMixin.__init__(self)



class Subscription:

    def __init__(self, state):
        self.state = state

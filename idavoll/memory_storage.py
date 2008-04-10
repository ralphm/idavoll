# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

import copy
from zope.interface import implements
from twisted.internet import defer
from twisted.words.protocols.jabber import jid

from idavoll import error, iidavoll

default_config = {"pubsub#persist_items": True,
                  "pubsub#deliver_payloads": True,
                  "pubsub#send_last_published_item": 'on_sub',
                  "pubsub#node_type": "leaf"}

class Storage:

    implements(iidavoll.IStorage)

    def __init__(self):
        self._nodes = {}

    def get_node(self, node_id):
        try:
            node = self._nodes[node_id]
        except KeyError:
            return defer.fail(error.NodeNotFound())

        return defer.succeed(node)

    def get_node_ids(self):
        return defer.succeed(self._nodes.keys())

    def create_node(self, node_id, owner, config=None):
        if node_id in self._nodes:
            return defer.fail(error.NodeExists())

        if not config:
            config = copy.copy(default_config)

        if config['pubsub#node_type'] != 'leaf':
            raise NotImplementedError

        node = LeafNode(node_id, owner, config)
        self._nodes[node_id] = node

        return defer.succeed(None)

    def delete_node(self, node_id):
        try:
            del self._nodes[node_id]
        except KeyError:
            return defer.fail(error.NodeNotFound())

        return defer.succeed(None)

    def get_affiliations(self, entity):
        entity = entity.userhost()
        return defer.succeed([(node.id, node._affiliations[entity])
                              for name, node in self._nodes.iteritems()
                              if entity in node._affiliations])

    def get_subscriptions(self, entity):
        subscriptions = []
        for node in self._nodes.itervalues():
            for subscriber, subscription in node._subscriptions.iteritems():
                subscriber = jid.internJID(subscriber)
                if subscriber.userhostJID() == entity.userhostJID():
                    subscriptions.append((node.id, subscriber,
                                          subscription.state))

        return defer.succeed(subscriptions)


class Node:

    implements(iidavoll.INode)

    def __init__(self, node_id, owner, config):
        self.id = node_id
        self._affiliations = {owner.userhost(): 'owner'}
        self._subscriptions = {}
        self._config = config

    def get_type(self):
        return self.type

    def get_configuration(self):
        return self._config

    def get_meta_data(self):
        config = copy.copy(self._config)
        config["pubsub#node_type"] = self.type
        return config

    def set_configuration(self, options):
        for option in options:
            if option in self._config:
                self._config[option] = options[option]

        return defer.succeed(None)

    def get_affiliation(self, entity):
        return defer.succeed(self._affiliations.get(entity.full()))

    def get_subscription(self, subscriber):
        try:
            subscription = self._subscriptions[subscriber.full()]
        except KeyError:
            state = None
        else:
            state = subscription.state
        return defer.succeed(state)

    def add_subscription(self, subscriber, state):
        if self._subscriptions.get(subscriber.full()):
            return defer.fail(error.SubscriptionExists())

        subscription = Subscription(state)
        self._subscriptions[subscriber.full()] = subscription
        return defer.succeed(None)

    def remove_subscription(self, subscriber):
        try:
            del self._subscriptions[subscriber.full()]
        except KeyError:
            return defer.fail(error.NotSubscribed())

        return defer.succeed(None)

    def get_subscribers(self):
        subscribers = [jid.internJID(subscriber) for subscriber, subscription
                       in self._subscriptions.iteritems()
                       if subscription.state == 'subscribed']

        return defer.succeed(subscribers)

    def is_subscribed(self, entity):
        for subscriber, subscription in self._subscriptions.iteritems():
            if jid.internJID(subscriber).userhost() == entity.userhost() and \
                    subscription.state == 'subscribed':
                return defer.succeed(True)

        return defer.succeed(False)

    def get_affiliations(self):
        affiliations = [(jid.internJID(entity), affiliation) for entity, affiliation
                       in self._affiliations.iteritems()]

        return defer.succeed(affiliations)


class LeafNodeMixin:

    type = 'leaf'

    def __init__(self):
        self._items = {}
        self._itemlist = []

    def store_items(self, items, publisher):
        for data in items:
            id = data["id"]
            data = data.toXml()
            if isinstance(data, str):
                data = data.decode('utf-8')
            item = (data, publisher)
            if id in self._items:
                self._itemlist.remove(self._items[id])
            self._items[id] = item
            self._itemlist.append(item)

        return defer.succeed(None)

    def remove_items(self, item_ids):
        deleted = []

        for item_id in item_ids:
            try:
                item = self._items[item_id]
            except KeyError:
                pass
            else:
                self._itemlist.remove(item)
                del self._items[item_id]
                deleted.append(item_id)

        return defer.succeed(deleted)

    def get_items(self, max_items=None):
        if max_items:
            list = self._itemlist[-max_items:]
        else:
            list = self._itemlist
        return defer.succeed([item[0] for item in list])

    def get_items_by_id(self, item_ids):
        items = []
        for item_id in item_ids:
            try:
                item = self._items[item_id]
            except KeyError:
                pass
            else:
                items.append(item[0])
        return defer.succeed(items)

    def purge(self):
        self._items = {}
        self._itemlist = []

        return defer.succeed(None)


class LeafNode(Node, LeafNodeMixin):

    implements(iidavoll.ILeafNode)

    def __init__(self, node_id, owner, config):
        Node.__init__(self, node_id, owner, config)
        LeafNodeMixin.__init__(self)


class Subscription:

    def __init__(self, state):
        self.state = state

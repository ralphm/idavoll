from twisted.application import service
from twisted.internet import defer
from twisted.protocols.jabber import jid
import backend

class Subscription:
    def __init__(self, state):
        self.state = state

class NodeConfiguration:
    def __init__(self):
        self.persist_items = False
        self.deliver_payloads = False

class Node:
    def __init__(self, id):
        self.id = id
        self.configuration = NodeConfiguration()
        self.subscriptions = {}
        self.affiliations = {}
        self.items = {}

class Storage:
    def __init__(self):
        self.nodes = {}

    def get_node_configuration(self, node_id):
        try:
            node = self.nodes[node_id]
        except KeyError:
            raise backend.NodeNotFound
        else:
            c = self.nodes[node_id].configuration
            return defer.succeed({'persist_items': c.persist_items,
                                  'deliver_payloads': c.deliver_payloads})

    def get_affiliation(self, node_id, entity):
        try:
            node = self.nodes[node_id]
        except KeyError:
            raise backend.NodeNotFound
        else:
            return defer.succeed(node.affiliations.get(entity.full(), None))

    def get_subscribers(self, node_id):
        try:
            node = self.nodes[node_id]
        except KeyError:
            raise backend.NodeNotFound
        else:
            subscriptions = self.nodes[node_id].subscriptions
            subscribers = [jid.JID(s) for s in subscriptions
                             if subscriptions[s].state == 'subscribed']
            return defer.succeed(subscribers)

    def store_items(self, node_id, items, publisher):
        for item in items:
            self.nodes[node_id].items[item["id"]] = (item, publisher)
        return defer.succeed(None)

    def add_subscription(self, node_id, subscriber, state):
        try:
            node = self.nodes[node_id]
        except KeyError:
            raise backend.NodeNotFound

        try:
            subscription = node.subscriptions[subscriber.full()]
        except:
            subscription = Subscription(state)
            node.subscriptions[subscriber.full()] = subscription

        return defer.succeed({'node': node_id,
                              'jid': subscriber,
                              'subscription': subscription.state})

    def remove_subscription(self, node_id, subscriber):
        try:
            node = self.nodes[node_id]
        except KeyError:
            raise backend.NodeNotFound

        try:
            del node.subscriptions[subscriber.full()]
        except KeyError:
            raise backend.NotSubscribed

        return defer.succeed(None)

    def create_node(self, node_id, owner):
        if node_id in self.nodes:
            raise backend.NodeExists
    
        node = Node(node_id)
        node.affiliations[owner.full()] = 'owner'
        self.nodes[node_id] = node

        return defer.succeed(None)

    def get_affiliations(self, entity):
        affiliations = []
        for node in self.nodes.itervalues():
            if entity.full() in node.affiliations:
                affiliations.append((node.id,
                                     node.affiliations[entity.full()]))

        return defer.succeed(affiliations)

    def get_subscriptions(self, entity):
        subscriptions = []
        for node in self.nodes.itervalues():
            for subscriber, subscription in node.subscriptions.iteritems():
                subscriber_jid = jid.JID(subscriber)
                if subscriber_jid.userhostJID() == entity:
                    subscriptions.append((node.id, subscriber_jid,
                                          subscription.state))
        return defer.succeed(subscriptions)

    def get_node_type(self, node_id):
        if node_id not in self.nodes:
            raise backend.NodeNotFound

        return defer.succeed('leaf')

    def get_nodes(self):
        return defer.succeed(self.nodes.keys())

class BackendService(backend.BackendService):
    pass

class NodeCreationService(backend.NodeCreationService):
    pass

class PublishService(backend.PublishService):
    pass

class NotificationService(backend.NotificationService):
    pass

class SubscriptionService(backend.SubscriptionService):
    pass

class AffiliationsService(backend.AffiliationsService):
    pass

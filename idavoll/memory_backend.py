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

        node = Node("ralphm/mood/ralphm@ik.nu")
        node.subscriptions["ralphm@doe.ik.nu"] = Subscription("subscribed")
        node.subscriptions["notify@ik.nu/mood_monitor"] = Subscription("subscribed")
        node.affiliations["ralphm@ik.nu"] = "owner"
        node.affiliations["ralphm@doe.ik.nu"] = "publisher"
        node.configuration.persist_items = True
        node.configuration.deliver_payloads = True
        self.nodes[node.id] = node

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

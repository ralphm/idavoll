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
            return defer.succeed(node.affiliations.get(entity, None))

    def get_subscribers(self, node_id):
        try:
            node = self.nodes[node_id]
        except KeyError:
            raise backend.NodeNotFound
        else:
            subscriptions = self.nodes[node_id].subscriptions
            subscribers = [s for s in subscriptions
                             if subscriptions[s].state == 'subscribed']
            return defer.succeed(subscribers)

    def store_items(self, node_id, items, publisher):
        for item in items:
            self.nodes[node_id].items[item["id"]] = (item, publisher)
            print self.nodes[node_id].items
        return defer.succeed(None)

class BackendService(backend.BackendService):

    def create_node(self, node_id, requestor):
        if not node_id:
            raise backend.NoInstantNodes

        if node_id in self.nodes:
            raise backend.NodeExists
    
        node = Node(node_id)
        node.affiliations[requestor.full()] = 'owner'
        self.nodes[node_id] = node

        return defer.succeed({'node_id': node.id})

    def subscribe(self, node_id, subscriber, requestor):
        # expect subscriber and requestor to be a jid.JID 
        try:
            node = self.nodes[node_id]
        except KeyError:
            raise backend.NodeNotFound

        if subscriber.userhostJID() != requestor:
            raise backend.NotAuthorized

        affiliation = node.affiliations.get(subscriber.full(), 'none')

        if affiliation == 'outcast':
            raise backend.NotAuthorized

        try:
            subscription = node.subscriptions[subscriber.full()]
        except KeyError:
            subscription = Subscription('subscribed')
            node.subscriptions[subscriber.full()] = subscription

        print node.subscriptions

        return defer.succeed({
                'affiliation': affiliation,
                'node': node_id,
                'jid': subscriber,
                'subscription': subscription.state})
    
    def unsubscribe(self, node_id, subscriber, requestor):
        try:
            node = self.nodes[node_id]
        except KeyError:
            raise backend.NodeNotFound

        if subscriber.userhostJID() != requestor:
            raise backend.NotAuthorized

        try:
            del node.subscriptions[subscriber.full()]
        except KeyError:
            raise backend.NotSubscribed

        return defer.succeed(None)

class NodeCreationService(service.Service):

    __implements__ = backend.INodeCreationService,

    def create_node(self, node_id, requestor):
        return self.parent.create_node(node_id, requestor)

class PublishService(service.Service):

    __implements__ = backend.IPublishService,
    
    def publish(self, node_id, items, requestor):
        return self.parent.publish(node_id, items, requestor)
    
class NotificationService(backend.NotificationService):

    __implements__ = backend.INotificationService,

    def get_notification_list(self, node_id, items):
        return self.parent.get_notification_list(node_id, items)

class SubscriptionService(service.Service):

    __implements__ = backend.ISubscriptionService,

    def subscribe(self, node_id, subscriber, requestor):
        return self.parent.subscribe(node_id, subscriber, requestor)

    def unsubscribe(self, node_id, subscriber, requestor):
        return self.parent.unsubscribe(node_id, subscriber, requestor)

class PersistenceService(service.Service):

    __implements__ = backend.IPersistenceService,

    def store_items(self, node_id, items, publisher):
        return self.parent.store_items(node_id, items, publisher)


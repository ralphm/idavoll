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

class BackendService(backend.BackendService):

    def __init__(self):
        backend.BackendService.__init__(self)

        self.nodes = {}

        node = Node("ralphm/mood/ralphm@ik.nu")
        node.subscriptions["ralphm@doe.ik.nu"] = Subscription("subscribed")
        node.subscriptions["notify@ik.nu/mood_monitor"] = Subscription("subscribed")
        node.affiliations["ralphm@ik.nu"] = "owner"
        node.affiliations["ralphm@doe.ik.nu"] = "publisher"
        node.configuration.persist_items = True
        node.configuration.deliver_payloads = True
        self.nodes[node.id] = node
    
    def get_supported_affiliations(self):
        return ['none', 'owner', 'outcast', 'publisher']

    def create_node(self, node_id, requestor):
        if not node_id:
            raise backend.NoInstantNodes

        if node_id in self.nodes:
            raise backend.NodeExists
    
        node = Node(node_id)
        node.affiliations[requestor.full()] = 'owner'
        self.nodes[node_id] = node

        return defer.succeed({'node_id': node.id})

    def publish(self, node_id, items, requestor):
        try:
            node = self.nodes[node_id]
            persist_items = node.configuration.persist_items
            deliver_payloads = node.configuration.deliver_payloads
        except KeyError:
            raise backend.NodeNotFound

        try:
            if node.affiliations[requestor.full()] not in \
               ['owner', 'publisher']:
                raise backend.NotAuthorized
        except KeyError:
            raise backend.NotAuthorized

        if items and not persist_items and not deliver_payloads:
            raise backend.NoPayloadAllowed
        elif not items and (persist_items or deliver_payloads):
            raise backend.PayloadExpected

        print "publish by %s to %s" % (requestor.full(), node_id)

        if persist_items or deliver_payloads:
            for item in items:
                if item["id"] is None:
                    item["id"] = 'random'   # FIXME

        if persist_items:
            self.store_items(node_id, items, requestor)

        if items and not deliver_payloads:
            for item in items:
                item.children = []

        self.dispatch({ 'items': items, 'node_id': node_id },
                             '//event/pubsub/notify')
        return defer.succeed(None)

    def get_notification_list(self, node_id, items):
        
        try:
            d = defer.succeed(self.nodes[node_id].subscriptions.keys())
        except:
            d = defer.fail()

        d.addCallback(self._magic_filter, node_id, items)

        return d

    def _magic_filter(self, subscribers, node_id, items):
        list = {}
        for subscriber in subscribers:
            list[subscriber] = items

        return list

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
    
    def store_items(self, node_id, items, publisher):
        for item in items:
            self.nodes[node_id].items[item["id"]] = item
            print self.nodes[node_id].items

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
        raise backend.NotImplemented

class PersistenceService(service.Service):

    __implements__ = backend.IPersistenceService,

    def store_items(self, node_id, items, publisher):
        return self.parent.store_items(node_id, items, publisher)


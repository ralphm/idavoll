from twisted.protocols.jabber import jid
from twisted.python import components
from twisted.application import service
from twisted.xish import utility
from twisted.internet import defer

class Error(Exception):
    msg = ''

    def __str__(self):
        return self.msg
    
class NodeNotFound(Error):
    msg = 'Node not found'

class NotAuthorized(Error):
    pass

class PayloadExpected(Error):
    msg = 'Payload expected'

class NoPayloadAllowed(Error):
    msg = 'No payload allowed'

class NoInstantNodes(Error):
    pass

class NodeExists(Error):
    pass

class NotImplemented(Error):
    pass

class NotSubscribed(Error):
    pass

class IBackendService(components.Interface):
    """ Interface to a backend service of a pubsub service. """

    def get_supported_affiliations(self):
        """ Reports the list of supported affiliation types.
    
        @return: a list of supported affiliation types.
        """

class INodeCreationService(components.Interface):
    """ A service for creating nodes """

    def create_node(self, node_id, requestor):
        """ Create a node.
        
        @return: a deferred that fires when the node has been created.
        """

class IPublishService(components.Interface):
    """ A service for publishing items to a node. """

    def publish(self, node_id, items, requestor):
        """ Publish items to a pubsub node.
        
        @return: a deferred that fires when the items have been published.
        """
class INotificationService(components.Interface):
    """ A service for notification of published items. """

    def register_notifier(self, observerfn, *args, **kwargs):
        """ Register callback which is called for notification. """

    def get_notification_list(self, node_id, items):
        pass

class ISubscriptionService(components.Interface):
    """ A service for managing subscriptions. """

    def subscribe(self, node_id, subscriber, requestor):
        """ Request the subscription of an entity to a pubsub node.

        Depending on the node's configuration and possible business rules, the
        C{subscriber} is added to the list of subscriptions of the node with id
        C{node_id}. The C{subscriber} might be different from the C{requestor},
        and if the C{requestor} is not allowed to subscribe this entity an
        exception should be raised.

        @return: a deferred that returns the subscription state
        """

    def unsubscribe(self, node_id, subscriber, requestor):
        """ Cancel the subscription of an entity to a pubsub node.

        The subscription of C{subscriber} is removed from the list of
        subscriptions of the node with id C{node_id}. If the C{requestor}
        is not allowed to unsubscribe C{subscriber}, an an exception should
        be raised.

        @return: a deferred that fires when unsubscription is complete.
        """

class IAffiliationsService(components.Interface):
    """ A service for retrieving the affiliations with this pubsub service. """

    def get_affiliations(self, entity):
        """ Report the list of current affiliations with this pubsub service.

        Report the list of the current affiliations with all nodes within this
        pubsub service, along with subscriptions to such nodes, for the
        C{entity}.

        @return: a deferred that returns the list of all current affiliations
        and subscriptions.
        """

class IRetractionService(components.Interface):
    """ A service for retracting published items """

    def retract_item(self, node_id, item_id, requestor):
        """ Removes item in node from persistent storage """

    def purge_node(self, node_id, requestor):
        """ Removes all items in node from persistent storage """

class IItemRetrievalService(components.Interface):
    """ A service for retrieving previously published items. """

    def get_items(self, node_id, max_items=None, item_ids=[],
                  requestor=None):
        """ Retrieve items from persistent storage

        If C{max_items} is given, return the C{max_items} last published
        items, else if C{item_ids} is not empty, return the items requested.
        If neither is given, return all items.

        @return: a deferred that returns the requested items
        """

class BackendService(service.MultiService, utility.EventDispatcher):

    __implements__ = IBackendService,

    def __init__(self, storage):
        service.MultiService.__init__(self)
        utility.EventDispatcher.__init__(self)
        self.storage = storage

    def supports_publisher_affiliation(self):
        return True

    def supports_outcast_affiliation(self):
        return True

    def supports_persistent_items(self):
        return True

class PublishService(service.Service):
    
    __implements__ = IPublishService,

    def publish(self, node_id, items, requestor):
        d1 = self.parent.storage.get_node_configuration(node_id)
        d2 = self.parent.storage.get_affiliation(node_id, requestor)
        d = defer.DeferredList([d1, d2], fireOnOneErrback=1)
        d.addErrback(lambda x: x.value[0])
        d.addCallback(self._do_publish, node_id, items, requestor)
        return d

    def _do_publish(self, result, node_id, items, requestor):
        configuration = result[0][1]
        persist_items = configuration["persist_items"]
        deliver_payloads = configuration["deliver_payloads"]
        affiliation = result[1][1]

        if affiliation not in ['owner', 'publisher']:
            raise NotAuthorized

        if items and not persist_items and not deliver_payloads:
            raise NoPayloadAllowed
        elif not items and (persist_items or deliver_payloads):
            raise PayloadExpected

        print "publish by %s to %s" % (requestor.full(), node_id)

        if persist_items or deliver_payloads:
            for item in items:
                if item["id"] is None:
                    item["id"] = 'random'   # FIXME

        if persist_items:
            d = self.parent.storage.store_items(node_id, items,
                                                requestor)
        else:
            d = defer.succeed(None)

        d.addCallback(self._do_notify, node_id, items, deliver_payloads)

    def _do_notify(self, result, node_id, items, deliver_payloads):
        if items and not deliver_payloads:
            for item in items:
                item.children = []

        self.parent.dispatch({ 'items': items, 'node_id': node_id },
                             '//event/pubsub/notify')

class NotificationService(service.Service):

    __implements__ = INotificationService,

    def get_notification_list(self, node_id, items):
        d = self.parent.storage.get_subscribers(node_id)
        d.addCallback(self._magic_filter, node_id, items)
        return d

    def _magic_filter(self, subscribers, node_id, items):
        list = {}
        for subscriber in subscribers:
            list[subscriber] = items
        return list

    def register_notifier(self, observerfn, *args, **kwargs):
        self.parent.addObserver('//event/pubsub/notify', observerfn,
                                *args, **kwargs)

class SubscriptionService(service.Service):

    __implements__ = ISubscriptionService,

    def subscribe(self, node_id, subscriber, requestor):
        if subscriber.userhostJID() != requestor:
            raise NotAuthorized

        d1 = self.parent.storage.get_node_configuration(node_id)
        d2 = self.parent.storage.get_affiliation(node_id, subscriber)
        d = defer.DeferredList([d1, d2], fireOnOneErrback=1)
        d.addErrback(lambda x: x.value[0])
        d.addCallback(self._do_subscribe, node_id, subscriber)
        return d

    def _do_subscribe(self, result, node_id, subscriber):
        configuration = result[0][1]
        affiliation = result[1][1]

        if affiliation == 'outcast':
            raise NotAuthorized

        d = self.parent.storage.add_subscription(node_id, subscriber,
                                                 'subscribed')
        d.addCallback(self._return_subscription, affiliation)
        return d

    def _return_subscription(self, result, affiliation):
        result['affiliation'] = affiliation
        return result

    def unsubscribe(self, node_id, subscriber, requestor):
        if subscriber.userhostJID() != requestor:
            raise NotAuthorized

        d = self.parent.storage.get_node_configuration(node_id)
        d.addCallback(self._do_unsubscribe, node_id, subscriber)
        return d

    def _do_unsubscribe(self, result, node_id, subscriber):
        return self.parent.storage.remove_subscription(node_id,
                                                       subscriber)

class NodeCreationService(service.Service):

    __implements__ = INodeCreationService,

    def supports_instant_nodes(self):
        return False

    def create_node(self, node_id, requestor):
        if not node_id:
            raise NoInstantNodes

        d = self.parent.storage.create_node(node_id, requestor)
        d.addCallback(lambda _: node_id)
        return d

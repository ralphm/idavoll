from zope.interface import Interface
import storage

class Error(Exception):
    msg = ''

    def __str__(self):
        return self.msg
    
class NotAuthorized(Error):
    pass

class PayloadExpected(Error):
    msg = 'Payload expected'

class NoPayloadAllowed(Error):
    msg = 'No payload allowed'

class NoInstantNodes(Error):
    pass

class NotImplemented(Error):
    pass

class NotSubscribed(Error):
    pass

class InvalidConfigurationOption(Error):
    msg = 'Invalid configuration option'

class InvalidConfigurationValue(Error):
    msg = 'Bad configuration value'

class IBackendService(Interface):
    """ Interface to a backend service of a pubsub service. """

    def __init__(self, storage):
        """
        @param storage: L{storage} object.
        """

    def supports_publisher_affiliation(self):
        """ Reports if the backend supports the publisher affiliation.
    
        @rtype: C{bool}
        """

    def supports_outcast_affiliation(self):
        """ Reports if the backend supports the publisher affiliation.
    
        @rtype: C{bool}
        """

    def supports_persistent_items(self):
        """ Reports if the backend supports persistent items.
    
        @rtype: C{bool}
        """

    def get_node_type(self, node_id):
        """ Return type of a node.

        @return: a deferred that returns either 'leaf' or 'collection'
        """

    def get_nodes(self):
        """ Returns list of all nodes.

        @return: a deferred that returns a C{list} of node ids.
        """

    def get_node_meta_data(self, node_id):
        """ Return meta data for a node.

        @return: a deferred that returns a C{list} of C{dict}s with the
                 metadata.
        """

class INodeCreationService(Interface):
    """ A service for creating nodes """

    def create_node(self, node_id, requestor):
        """ Create a node.
        
        @return: a deferred that fires when the node has been created.
        """

class INodeDeletionService(Interface):
    """ A service for deleting nodes. """

    def register_pre_delete(self, pre_delete_fn):
        """ Register a callback that is called just before a node deletion.
        
        The function C{pre_deleted_fn} is added to a list of functions
        to be called just before deletion of a node. The callback
        C{pre_delete_fn} is called with the C{node_id} that is about to be
        deleted and should return a deferred that returns a list of deferreds
        that are to be fired after deletion. The backend collects the lists
        from all these callbacks before actually deleting the node in question.
        After deletion all collected deferreds are fired to do post-processing.

        The idea is that you want to be able to collect data from the
        node before deleting it, for example to get a list of subscribers
        that have to be notified after the node has been deleted. To do this,
        C{pre_delete_fn} fetches the subscriber list and passes this
        list to a callback attached to a deferred that it sets up. This
        deferred is returned in the list of deferreds.
        """

    def get_subscribers(self, node_id):
        """ Get node subscriber list.
        
        @return: a deferred that fires with the list of subscribers.
        """

    def delete_node(self, node_id, requestor):
        """ Delete a node.
        
        @return: a deferred that fires when the node has been deleted.
        """

class IPublishService(Interface):
    """ A service for publishing items to a node. """

    def publish(self, node_id, items, requestor):
        """ Publish items to a pubsub node.
        
        @return: a deferred that fires when the items have been published.
        """
class INotificationService(Interface):
    """ A service for notification of published items. """

    def register_notifier(self, observerfn, *args, **kwargs):
        """ Register callback which is called for notification. """

    def get_notification_list(self, node_id, items):
        pass

class ISubscriptionService(Interface):
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

class IAffiliationsService(Interface):
    """ A service for retrieving the affiliations with this pubsub service. """

    def get_affiliations(self, entity):
        """ Report the list of current affiliations with this pubsub service.

        Report the list of the current affiliations with all nodes within this
        pubsub service, along with subscriptions to such nodes, for the
        C{entity}.

        @return: a deferred that returns the list of all current affiliations
        and subscriptions.
        """

class IRetractionService(Interface):
    """ A service for retracting published items """

    def retract_item(self, node_id, item_id, requestor):
        """ Removes item in node from persistent storage """

    def purge_node(self, node_id, requestor):
        """ Removes all items in node from persistent storage """

class IItemRetrievalService(Interface):
    """ A service for retrieving previously published items. """

    def get_items(self, node_id, requestor, max_items=None, item_ids=[]):
        """ Retrieve items from persistent storage

        If C{max_items} is given, return the C{max_items} last published
        items, else if C{item_ids} is not empty, return the items requested.
        If neither is given, return all items.

        @return: a deferred that returns the requested items
        """

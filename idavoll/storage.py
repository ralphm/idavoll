from zope.interface import Interface
from twisted.words.protocols.jabber import jid
from twisted.xish import domish

class Error(Exception):
    msg = None

class NodeNotFound(Error):
    pass

class NodeExists(Error):
    pass

class SubscriptionNotFound(Error):
    pass

class SubscriptionExists(Error):
    pass

class ItemNotFound(Error):
    pass

class IStorage(Interface):
    """ Storage interface """

    def get_node(self, node_id):
        """ Get Node.

        @param node_id: NodeID of the desired node.
        @type node_id: L{str}
        @return: deferred that returns a L{Node} object.
        """

    def get_node_ids(self):
        """ Return all NodeIDs.
        
        @return: deferred that returns a list of NodeIDs (L{str}).
        """

    def create_node(self, node_id, owner, config = None, type='leaf'):
        """ Create new node.

        The implementation should make sure, the passed owner JID is stripped
        of the resource (e.g. using C{owner.userhostJID()}).

        @param node_id: NodeID of the new node.
        @type node_id: L{str}
        @param owner: JID of the new nodes's owner. 
        @type owner: L{jid.JID}
        @param config: Configuration
        @param type: Node type. Can be either C{'leaf'} or C{'collection'}.
        @return: deferred that fires on creation.
        """

    def delete_node(self, node_id):
        """ Delete a node.

        @param node_id: NodeID of the new node.
        @type node_id: L{str}
        @return: deferred that fires on deletion.
        """

    def get_affiliations(self, entity):
        """ Get all affiliations for entity.
        
        The implementation should make sure, the passed owner JID is stripped
        of the resource (e.g. using C{owner.userhostJID()}).
        
        @param entity: JID of the entity.
        @type entity: L{jid.JID}
        @return: deferred that returns a L{list} of tuples of the form
                 C{(node_id, affiliation)}, where C{node_id} is of the type
                 L{str} and C{affiliation} is one of C{'owner'}, C{'publisher'}
                 and C{'outcast'}.
        """

    def get_subscriptions(self, entity):
        """ Get all subscriptions for an entity.
        
        The implementation should make sure, the passed owner JID is stripped
        of the resource (e.g. using C{owner.userhostJID()}).

        @param entity: JID of the entity.
        @type entity: L{jid.JID}
        @return: deferred that returns a L{list} of tuples of the form
                 C{(node_id, subscriber, state)}, where C{node_id} is of the
                 type L{str}, C{subscriber} of the type {jid.JID}, and
                 C{state} is C{'subscribed'} or C{'pending'}.
        """


class INode(Interface):
    """ Interface to the class of objects that represent nodes. """

    def get_type(self):
        """ Get node's type.
        
        @return: C{'leaf'} or C{'collection'}.
        """

    def get_configuration(self):
        """ Get node's configuration.

        The configuration must at least have two options:
        C{pubsub#persist_items}, and C{pubsub#deliver_payloads}.

        @return: L{dict} of configuration options.
        """

    def get_meta_data(self):
        """ Get node's meta data.

        The meta data must be a superset of the configuration options, and
        also at least should have a C{pubsub#node_type} entry.

        @return: L{dict} of meta data.
        """

    def set_configuration(self, options):
        """ Set node's configuration.
        
        The elements of {options} will set the new values for those
        configuration items. This means that only changing items have to
        be given.

        @param options: a dictionary of configuration options.
        @returns: a deferred that fires upon success.
        """

    def get_affiliation(self, entity):
        """ Get affiliation of entity with this node.

        @param entity: JID of entity.
        @type entity: L{jid.JID}
        @return: deferred that returns C{'owner'}, C{'publisher'}, C{'outcast'}
                 or C{None}.
        """

    def get_subscription(self, subscriber):
        """ Get subscription to this node of subscriber.

        @param subscriber: JID of the new subscriptions' entity.
        @type subscriber: L{jid.JID}
        @return: deferred that returns the subscription state (C{'subscribed'},
                 C{'pending'} or C{None}).
        """

    def add_subscription(self, subscriber, state):
        """ Add new subscription to this node with given state.

        @param subscriber: JID of the new subscriptions' entity.
        @type subscriber: L{jid.JID}
        @param state: C{'subscribed'} or C{'pending'}
        @type state: L{str}
        @return: deferred that fires on subscription.
        """

    def remove_subscription(self, subscriber):
        """ Remove subscription to this node.

        @param subscriber: JID of the subscriptions' entity.
        @type subscriber: L{jid.JID}
        @return: deferred that fires on removal.
        """

    def get_subscribers(self):
        """ Get list of subscribers to this node.
        
        Retrieves the list of entities that have a subscription to this
        node. That is, having the state C{'subscribed'}.

        @return: a deferred that returns a L{list} of L{jid.JID}s.
        """

    def is_subscribed(self, subscriber):
        """ Returns whether subscriber has a subscription to this node.
       
        Only returns C{True} when the subscription state (if present) is
        C{'subscribed'}.

        @param subscriber: JID of the subscriptions' entity.
        @type subscriber: L{jid.JID}
        @return: deferred that returns a L{bool}.
        """

class ILeafNode(Interface):
    """ Interface to the class of objects that represent leaf nodes. """

    def store_items(self, items, publisher):
        """ Store items in persistent storage for later retrieval.
        
        @param items: The list of items to be stored. Each item is the
                      L{domish} representation of the XML fragment as defined
                      for C{<item/>} in the
                      C{http://jabber.org/protocol/pubsub} namespace.
        @type items: L{list} of {domish.Element}
        @param publisher: JID of the publishing entity.
        @type publisher: L{jid.JID}
        @return: deferred that fires upon success.
        """

    def remove_items(self, item_ids):
        """ Remove items by id
        
        @param item_ids: L{list} of item ids.
        @return: deferred that fires when all given items were deleted, or
                 a failure if one of them was not found.
        """

    def get_items(self, max_items=None):
        """ Get items.

        If C{max_items} is not given, all items in the node are returned,
        just like C{get_items_by_id}. Otherwise, C{max_items} limits
        the returned items to a maximum of that number of most recently
        published items.
       
        @param max_items: if given, a natural number (>0) that limits the
                          returned number of items.
        @return: deferred that fires with a C{list} of found items.
        """

    def get_items_by_id(self, item_ids):
        """ Get items by item id.

        Each item in the returned list is a unicode string that
        represent the XML of the item as it was published, including the
        item wrapper with item id.
        
        @param item_ids: L{list} of item ids.
        @return: deferred that fires with a C{list} of found items.
        """

    def purge(self):
        """ Purge node of all items in persistent storage.
        
        @return: deferred that fires when the node has been purged.
        """


class ISubscription(Interface):
    """ """

from zope.interface import Interface
from twisted.words.protocols.jabber import jid

class Error(Exception):
    msg = None

class NodeNotFound(Error):
    pass


class NodeExists(Error):
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
    """ """
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
        """ """

    def get_affiliation(self, entity):
        """ """

    def add_subscription(self, subscriber, state):
        """ """

    def remove_subscription(self, subscriber):
        """ """

    def get_subscribers(self):
        """ """

    def is_subscribed(self, subscriber):
        """ """


class ILeafNode(Interface):
    """ """
    def store_items(self, items, publisher):
        """ """

    def remove_items(self, item_ids):
        """ """

    def get_items(self, max_items=None):
        """ """

    def get_items_by_id(self, item_ids):
        """ """

    def purge(self):
        """ """


class ISubscription(Interface):
    """ """

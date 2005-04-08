from zope.interface import Interface

class Error(Exception):
    msg = None

class NodeNotFound(Error):
    pass


class NodeExists(Error):
    pass


class IStorage(Interface):
    """ """

    def get_node(self, node_id):
        """ """

    def get_node_ids(self):
        """ """

    def create_node(self, node_id, owner, config = None, type='leaf'):
        """ """

    def delete_node(self, node_id):
        """ """

    def get_affiliations(self, entity):
        """ """

    def get_subscriptions(self, entity):
        """ """


class INode(Interface):
    """ """
    def get_type(self):
        """ """

    def get_configuration(self):
        """ """

    def get_meta_data(self):
        """ """

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

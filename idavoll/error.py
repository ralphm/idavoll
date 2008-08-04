# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

class Error(Exception):
    msg = ''

    def __str__(self):
        return self.msg



class NodeNotFound(Error):
    pass



class NodeExists(Error):
    pass



class NotSubscribed(Error):
    """
    Entity is not subscribed to this node.
    """



class SubscriptionExists(Error):
    """
    There already exists a subscription to this node.
    """



class Forbidden(Error):
    pass



class ItemForbidden(Error):
    pass



class ItemRequired(Error):
    pass



class NoInstantNodes(Error):
    pass



class InvalidConfigurationOption(Error):
    msg = 'Invalid configuration option'



class InvalidConfigurationValue(Error):
    msg = 'Bad configuration value'



class NodeNotPersistent(Error):
    pass



class NoRootNode(Error):
    pass



class NoCallbacks(Error):
    """
    There are no callbacks for this node.
    """



class NoCollections(Error):
    pass



class NoPublishing(Error):
    """
    This node does not support publishing.
    """

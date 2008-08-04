# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

"""
Interfaces for idavoll.
"""

from zope.interface import Attribute, Interface

class IBackendService(Interface):
    """ Interface to a backend service of a pubsub service. """


    def __init__(storage):
        """
        @param storage: Object providing L{IStorage}.
        """


    def supportsPublisherAffiliation():
        """ Reports if the backend supports the publisher affiliation.

        @rtype: C{bool}
        """


    def supportsOutcastAffiliation():
        """ Reports if the backend supports the publisher affiliation.

        @rtype: C{bool}
        """


    def supportsPersistentItems():
        """ Reports if the backend supports persistent items.

        @rtype: C{bool}
        """


    def getNodeType(nodeIdentifier):
        """ Return type of a node.

        @return: a deferred that returns either 'leaf' or 'collection'
        """


    def getNodes():
        """ Returns list of all nodes.

        @return: a deferred that returns a C{list} of node ids.
        """


    def getNodeMetaData(nodeIdentifier):
        """ Return meta data for a node.

        @return: a deferred that returns a C{list} of C{dict}s with the
                 metadata.
        """


    def createNode(nodeIdentifier, requestor):
        """ Create a node.

        @return: a deferred that fires when the node has been created.
        """


    def registerPreDelete(preDeleteFn):
        """ Register a callback that is called just before a node deletion.

        The function C{preDeletedFn} is added to a list of functions to be
        called just before deletion of a node. The callback C{preDeleteFn} is
        called with the C{nodeIdentifier} that is about to be deleted and
        should return a deferred that returns a list of deferreds that are to
        be fired after deletion. The backend collects the lists from all these
        callbacks before actually deleting the node in question.  After
        deletion all collected deferreds are fired to do post-processing.

        The idea is that you want to be able to collect data from the node
        before deleting it, for example to get a list of subscribers that have
        to be notified after the node has been deleted. To do this,
        C{preDeleteFn} fetches the subscriber list and passes this list to a
        callback attached to a deferred that it sets up. This deferred is
        returned in the list of deferreds.
        """


    def deleteNode(nodeIdentifier, requestor):
        """ Delete a node.

        @return: a deferred that fires when the node has been deleted.
        """


    def purgeNode(nodeIdentifier, requestor):
        """ Removes all items in node from persistent storage """


    def subscribe(nodeIdentifier, subscriber, requestor):
        """ Request the subscription of an entity to a pubsub node.

        Depending on the node's configuration and possible business rules, the
        C{subscriber} is added to the list of subscriptions of the node with id
        C{nodeIdentifier}. The C{subscriber} might be different from the
        C{requestor}, and if the C{requestor} is not allowed to subscribe this
        entity an exception should be raised.

        @return: a deferred that returns the subscription state
        """


    def unsubscribe(nodeIdentifier, subscriber, requestor):
        """ Cancel the subscription of an entity to a pubsub node.

        The subscription of C{subscriber} is removed from the list of
        subscriptions of the node with id C{nodeIdentifier}. If the
        C{requestor} is not allowed to unsubscribe C{subscriber}, an an
        exception should be raised.

        @return: a deferred that fires when unsubscription is complete.
        """


    def getSubscribers(nodeIdentifier):
        """ Get node subscriber list.

        @return: a deferred that fires with the list of subscribers.
        """


    def getSubscriptions(entity):
        """ Report the list of current subscriptions with this pubsub service.

        Report the list of the current subscriptions with all nodes within this
        pubsub service, for the C{entity}.

        @return: a deferred that returns the list of all current subscriptions
                 as tuples C{(nodeIdentifier, subscriber, subscription)}.
        """


    def getAffiliations(entity):
        """ Report the list of current affiliations with this pubsub service.

        Report the list of the current affiliations with all nodes within this
        pubsub service, for the C{entity}.

        @return: a deferred that returns the list of all current affiliations
                 as tuples C{(nodeIdentifier, affiliation)}.
        """


    def publish(nodeIdentifier, items, requestor):
        """ Publish items to a pubsub node.

        @return: a deferred that fires when the items have been published.
        @rtype: L{Deferred<twisted.internet.defer.Deferred>}
        """


    def registerNotifier(observerfn, *args, **kwargs):
        """ Register callback which is called for notification. """


    def getNotifications(nodeIdentifier, items):
        """
        Get notification list.

        This method is called to discover which entities should receive
        notifications for the given items that have just been published to the
        given node.

        The notification list contains tuples (subscriber, subscriptions,
        items) to result in one notification per tuple: the given subscriptions
        yielded the given items to be notified to this subscriber.  This
        structure is needed allow for letting the subscriber know which
        subscriptions yielded which notifications, while catering for
        collection nodes and content-based subscriptions.

        To minimize the amount of notifications per entity, implementers
        should take care that if all items in C{items} were yielded
        by the same set of subscriptions, exactly one tuple is for this
        subscriber is returned, so that the subscriber would get exactly one
        notification. Alternatively, one tuple per subscription combination.

        @param nodeIdentifier: The identifier of the node the items were
                               published to.
        @type nodeIdentifier: C{unicode}.
        @param items: The list of published items as
                      L{Element<twisted.words.xish.domish.Element>}s.
        @type items: C{list}
        @return: The notification list as tuples of
                 (L{JID<twisted.words.protocols.jabber.jid.JID>},
                  C{list} of L{Subscription<wokkel.pubsub.Subscription>},
                  C{list} of L{Element<twisted.words.xish.domish.Element>}.
        @rtype: C{list}
        """


    def getItems(nodeIdentifier, requestor, maxItems=None, itemIdentifiers=[]):
        """ Retrieve items from persistent storage

        If C{maxItems} is given, return the C{maxItems} last published
        items, else if C{itemIdentifiers} is not empty, return the items
        requested.  If neither is given, return all items.

        @return: a deferred that returns the requested items
        """


    def retractItem(nodeIdentifier, itemIdentifier, requestor):
        """ Removes item in node from persistent storage """



class IStorage(Interface):
    """
    Storage interface.
    """


    def getNode(nodeIdentifier):
        """
        Get Node.

        @param nodeIdentifier: NodeID of the desired node.
        @type nodeIdentifier: C{str}
        @return: deferred that returns a L{INode} providing object.
        """


    def getNodeIds():
        """
        Return all NodeIDs.

        @return: deferred that returns a list of NodeIDs (C{unicode}).
        """


    def createNode(nodeIdentifier, owner, config):
        """
        Create new node.

        The implementation should make sure, the passed owner JID is stripped
        of the resource (e.g. using C{owner.userhostJID()}). The passed config
        is expected to have values for the fields returned by
        L{getDefaultConfiguration}, as well as a value for
        C{'pubsub#node_type'}.

        @param nodeIdentifier: NodeID of the new node.
        @type nodeIdentifier: C{unicode}
        @param owner: JID of the new nodes's owner.
        @type owner: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param config: Node configuration.
        @type config: C{dict}
        @return: deferred that fires on creation.
        """


    def deleteNode(nodeIdentifier):
        """
        Delete a node.

        @param nodeIdentifier: NodeID of the new node.
        @type nodeIdentifier: C{unicode}
        @return: deferred that fires on deletion.
        """


    def getAffiliations(entity):
        """
        Get all affiliations for entity.

        The implementation should make sure, the passed owner JID is stripped
        of the resource (e.g. using C{owner.userhostJID()}).

        @param entity: JID of the entity.
        @type entity: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @return: deferred that returns a C{list} of tuples of the form
                 C{(nodeIdentifier, affiliation)}, where C{nodeIdentifier} is
                 of the type L{unicode} and C{affiliation} is one of
                 C{'owner'}, C{'publisher'} and C{'outcast'}.
        """


    def getSubscriptions(entity):
        """
        Get all subscriptions for an entity.

        The implementation should make sure, the passed owner JID is stripped
        of the resource (e.g. using C{owner.userhostJID()}).

        @param entity: JID of the entity.
        @type entity: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @return: deferred that returns a C{list} of tuples of the form
                 C{(nodeIdentifier, subscriber, state)}, where
                 C{nodeIdentifier} is of the type C{unicode}, C{subscriber} of
                 the type J{JID<twisted.words.protocols.jabber.jid.JID>}, and
                 C{state} is C{'subscribed'}, C{'pending'} or
                 C{'unconfigured'}.
        """


    def getDefaultConfiguration(nodeType):
        """
        Get the default configuration for the given node type.

        @param nodeType: Either C{'leaf'} or C{'collection'}.
        @type nodeType: C{str}
        @return: The default configuration.
        @rtype: C{dict}.
        @raises: L{idavoll.error.NoCollections} if collections are not
                 supported.
        """



class INode(Interface):
    """
    Interface to the class of objects that represent nodes.
    """

    nodeType = Attribute("""The type of this node. One of {'leaf'},
                           {'collection'}.""")
    nodeIdentifier = Attribute("""The node identifer of this node""")


    def getType():
        """
        Get node's type.

        @return: C{'leaf'} or C{'collection'}.
        """


    def getConfiguration():
        """
        Get node's configuration.

        The configuration must at least have two options:
        C{pubsub#persist_items}, and C{pubsub#deliver_payloads}.

        @return: C{dict} of configuration options.
        """


    def getMetaData():
        """
        Get node's meta data.

        The meta data must be a superset of the configuration options, and
        also at least should have a C{pubsub#node_type} entry.

        @return: C{dict} of meta data.
        """


    def setConfiguration(options):
        """
        Set node's configuration.

        The elements of {options} will set the new values for those
        configuration items. This means that only changing items have to
        be given.

        @param options: a dictionary of configuration options.
        @returns: a deferred that fires upon success.
        """


    def getAffiliation(entity):
        """
        Get affiliation of entity with this node.

        @param entity: JID of entity.
        @type entity: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @return: deferred that returns C{'owner'}, C{'publisher'}, C{'outcast'}
                 or C{None}.
        """


    def getSubscription(subscriber):
        """
        Get subscription to this node of subscriber.

        @param subscriber: JID of the new subscriptions' entity.
        @type subscriber: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @return: deferred that returns the subscription state (C{'subscribed'},
                 C{'pending'} or C{None}).
        """


    def getSubscriptions(state=None):
        """
        Get list of subscriptions to this node.

        The optional C{state} argument filters the subscriptions to their
        state.

        @param state: Subscription state filter. One of C{'subscribed'},
                      C{'pending'}, C{'unconfigured'}.
        @type state: C{str}
        @return: a deferred that returns a C{list} of
                 L{wokkel.pubsub.Subscription}s.
        """


    def addSubscription(subscriber, state, config):
        """
        Add new subscription to this node with given state.

        @param subscriber: JID of the new subscriptions' entity.
        @type subscriber: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param state: C{'subscribed'} or C{'pending'}
        @type state: C{str}
        @param config: Subscription configuration.
        @param config: C{dict}
        @return: deferred that fires on subscription.
        """


    def removeSubscription(subscriber):
        """
        Remove subscription to this node.

        @param subscriber: JID of the subscriptions' entity.
        @type subscriber: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @return: deferred that fires on removal.
        """


    def isSubscribed(entity):
        """
        Returns whether entity has any subscription to this node.

        Only returns C{True} when the subscription state (if present) is
        C{'subscribed'} for any subscription that matches the bare JID.

        @param subscriber: bare JID of the subscriptions' entity.
        @type subscriber: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @return: deferred that returns a C{bool}.
        """


    def getAffiliations():
        """
        Get affiliations of entities with this node.

        @return: deferred that returns a C{list} of tuples (jid, affiliation),
                 where jid is a L(JID<twisted.words.protocols.jabber.jid.JID>)
                 and affiliation is one of C{'owner'},
        C{'publisher'}, C{'outcast'}.
        """



class ILeafNode(Interface):
    """
    Interface to the class of objects that represent leaf nodes.
    """

    def storeItems(items, publisher):
        """
        Store items in persistent storage for later retrieval.

        @param items: The list of items to be stored. Each item is the
                      L{domish} representation of the XML fragment as defined
                      for C{<item/>} in the
                      C{http://jabber.org/protocol/pubsub} namespace.
        @type items: C{list} of {domish.Element}
        @param publisher: JID of the publishing entity.
        @type publisher: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @return: deferred that fires upon success.
        """


    def removeItems(itemIdentifiers):
        """
        Remove items by id.

        @param itemIdentifiers: C{list} of item ids.
        @return: deferred that fires with a C{list} of ids of the items that
                 were deleted
        """


    def getItems(maxItems=None):
        """
        Get items.

        If C{maxItems} is not given, all items in the node are returned,
        just like C{getItemsById}. Otherwise, C{maxItems} limits
        the returned items to a maximum of that number of most recently
        published items.

        @param maxItems: if given, a natural number (>0) that limits the
                          returned number of items.
        @return: deferred that fires with a C{list} of found items.
        """


    def getItemsById(itemIdentifiers):
        """
        Get items by item id.

        Each item in the returned list is a unicode string that
        represent the XML of the item as it was published, including the
        item wrapper with item id.

        @param itemIdentifiers: C{list} of item ids.
        @return: deferred that fires with a C{list} of found items.
        """


    def purge():
        """
        Purge node of all items in persistent storage.

        @return: deferred that fires when the node has been purged.
        """



class IGatewayStorage(Interface):

    def addCallback(service, nodeIdentifier, callback):
        """
        Register a callback URI.

        The registered HTTP callback URI will have an Atom Entry documented
        POSTed to it upon receiving a notification for the given pubsub node.

        @param service: The XMPP entity that holds the node.
        @type service: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param nodeIdentifier: The identifier of the publish-subscribe node.
        @type nodeIdentifier: C{unicode}.
        @param callback: The callback URI to be registered.
        @type callback: C{str}.
        @rtype: L{Deferred<twisted.internet.defer.Deferred>}
        """

    def removeCallback(service, nodeIdentifier, callback):
        """
        Remove a registered callback URI.

        The returned deferred will fire with a boolean that signals wether or
        not this was the last callback unregistered for this node.

        @param service: The XMPP entity that holds the node.
        @type service: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param nodeIdentifier: The identifier of the publish-subscribe node.
        @type nodeIdentifier: C{unicode}.
        @param callback: The callback URI to be unregistered.
        @type callback: C{str}.
        @rtype: L{Deferred<twisted.internet.defer.Deferred>}
        """

    def getCallbacks(service, nodeIdentifier):
        """
        Get the callbacks registered for this node.

        Returns a deferred that fires with the set of HTTP callback URIs
        registered for this node.

        @param service: The XMPP entity that holds the node.
        @type service: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param nodeIdentifier: The identifier of the publish-subscribe node.
        @type nodeIdentifier: C{unicode}.
        @rtype: L{Deferred<twisted.internet.defer.Deferred>}
        """


    def hasCallbacks(service, nodeIdentifier):
        """
        Return wether there are callbacks registered for a node.

        @param service: The XMPP entity that holds the node.
        @type service: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param nodeIdentifier: The identifier of the publish-subscribe node.
        @type nodeIdentifier: C{unicode}.
        @returns: Deferred that fires with a boolean.
        @rtype: L{Deferred<twisted.internet.defer.Deferred>}
        """

# -*- test-case-name: idavoll.test.test_backend -*-
#
# Copyright (c) 2003-2009 Ralph Meijer
# See LICENSE for details.

"""
Generic publish-subscribe backend.

This module implements a generic publish-subscribe backend service with
business logic as per
U{XEP-0060<http://www.xmpp.org/extensions/xep-0060.html>} that interacts with
a given storage facility. It also provides an adapter from the XMPP
publish-subscribe protocol.
"""

import uuid

from zope.interface import implements

from twisted.application import service
from twisted.python import components, log
from twisted.internet import defer, reactor
from twisted.words.protocols.jabber.error import StanzaError
from twisted.words.xish import domish, utility

from wokkel.iwokkel import IDisco, IPubSubService
from wokkel.pubsub import PubSubService, PubSubError

from idavoll import error, iidavoll
from idavoll.iidavoll import IBackendService, ILeafNode

def _getAffiliation(node, entity):
    d = node.getAffiliation(entity)
    d.addCallback(lambda affiliation: (node, affiliation))
    return d



class BackendService(service.Service, utility.EventDispatcher):
    """
    Generic publish-subscribe backend service.

    @cvar nodeOptions: Node configuration form as a mapping from the field
                       name to a dictionary that holds the field's type, label
                       and possible options to choose from.
    @type nodeOptions: C{dict}.
    @cvar defaultConfig: The default node configuration.
    """

    implements(iidavoll.IBackendService)

    nodeOptions = {
            "pubsub#persist_items":
                {"type": "boolean",
                 "label": "Persist items to storage"},
            "pubsub#deliver_payloads":
                {"type": "boolean",
                 "label": "Deliver payloads with event notifications"},
            "pubsub#send_last_published_item":
                {"type": "list-single",
                 "label": "When to send the last published item",
                 "options": {
                     "never": "Never",
                     "on_sub": "When a new subscription is processed"}
                },
            }

    subscriptionOptions = {
            "pubsub#subscription_type":
                {"type": "list-single",
                 "options": {
                     "items": "Receive notification of new items only",
                     "nodes": "Receive notification of new nodes only"}
                },
            "pubsub#subscription_depth":
                {"type": "list-single",
                 "options": {
                     "1": "Receive notification from direct child nodes only",
                     "all": "Receive notification from all descendent nodes"}
                },
            }

    def __init__(self, storage):
        utility.EventDispatcher.__init__(self)
        self.storage = storage
        self._callbackList = []


    def supportsPublisherAffiliation(self):
        return True


    def supportsOutcastAffiliation(self):
        return True


    def supportsPersistentItems(self):
        return True


    def getNodeType(self, nodeIdentifier):
        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(lambda node: node.getType())
        return d


    def getNodes(self):
        return self.storage.getNodeIds()


    def getNodeMetaData(self, nodeIdentifier):
        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(lambda node: node.getMetaData())
        d.addCallback(self._makeMetaData)
        return d


    def _makeMetaData(self, metaData):
        options = []
        for key, value in metaData.iteritems():
            if key in self.nodeOptions:
                option = {"var": key}
                option.update(self.nodeOptions[key])
                option["value"] = value
                options.append(option)

        return options


    def _checkAuth(self, node, requestor):
        def check(affiliation, node):
            if affiliation not in ['owner', 'publisher']:
                raise error.Forbidden()
            return node

        d = node.getAffiliation(requestor)
        d.addCallback(check, node)
        return d


    def publish(self, nodeIdentifier, items, requestor):
        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(self._checkAuth, requestor)
        d.addCallback(self._doPublish, items, requestor)
        return d


    def _doPublish(self, node, items, requestor):
        if node.nodeType == 'collection':
            raise error.NoPublishing()

        configuration = node.getConfiguration()
        persistItems = configuration["pubsub#persist_items"]
        deliverPayloads = configuration["pubsub#deliver_payloads"]

        if items and not persistItems and not deliverPayloads:
            raise error.ItemForbidden()
        elif not items and (persistItems or deliverPayloads):
            raise error.ItemRequired()

        if persistItems or deliverPayloads:
            for item in items:
                item.uri = None
                item.defaultUri = None
                if not item.getAttribute("id"):
                    item["id"] = str(uuid.uuid4())

        if persistItems:
            d = node.storeItems(items, requestor)
        else:
            d = defer.succeed(None)

        d.addCallback(self._doNotify, node.nodeIdentifier, items,
                      deliverPayloads)
        return d


    def _doNotify(self, result, nodeIdentifier, items, deliverPayloads):
        if items and not deliverPayloads:
            for item in items:
                item.children = []

        self.dispatch({'items': items, 'nodeIdentifier': nodeIdentifier},
                      '//event/pubsub/notify')


    def getNotifications(self, nodeIdentifier, items):

        def toNotifications(subscriptions, nodeIdentifier, items):
            subsBySubscriber = {}
            for subscription in subscriptions:
                if subscription.options.get('pubsub#subscription_type',
                                            'items') == 'items':
                    subs = subsBySubscriber.setdefault(subscription.subscriber,
                                                       set())
                    subs.add(subscription)

            notifications = [(subscriber, subscriptions, items)
                             for subscriber, subscriptions
                             in subsBySubscriber.iteritems()]

            return notifications

        def rootNotFound(failure):
            failure.trap(error.NodeNotFound)
            return []

        d1 = self.storage.getNode(nodeIdentifier)
        d1.addCallback(lambda node: node.getSubscriptions('subscribed'))
        d2 = self.storage.getNode('')
        d2.addCallback(lambda node: node.getSubscriptions('subscribed'))
        d2.addErrback(rootNotFound)
        d = defer.gatherResults([d1, d2])
        d.addCallback(lambda result: result[0] + result[1])
        d.addCallback(toNotifications, nodeIdentifier, items)
        return d


    def registerNotifier(self, observerfn, *args, **kwargs):
        self.addObserver('//event/pubsub/notify', observerfn, *args, **kwargs)


    def subscribe(self, nodeIdentifier, subscriber, requestor):
        subscriberEntity = subscriber.userhostJID()
        if subscriberEntity != requestor:
            return defer.fail(error.Forbidden())

        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(_getAffiliation, subscriberEntity)
        d.addCallback(self._doSubscribe, subscriber)
        return d


    def _doSubscribe(self, result, subscriber):
        node, affiliation = result

        if affiliation == 'outcast':
            raise error.Forbidden()

        def trapExists(failure):
            failure.trap(error.SubscriptionExists)
            return False

        def cb(sendLast):
            d = node.getSubscription(subscriber)
            if sendLast:
                d.addCallback(self._sendLastPublished, node)
            return d

        d = node.addSubscription(subscriber, 'subscribed', {})
        d.addCallbacks(lambda _: True, trapExists)
        d.addCallback(cb)
        return d


    def _sendLastPublished(self, subscription, node):

        def notifyItem(items):
            if items:
                reactor.callLater(0, self.dispatch,
                                     {'items': items,
                                      'nodeIdentifier': node.nodeIdentifier,
                                      'subscription': subscription},
                                     '//event/pubsub/notify')

        config = node.getConfiguration()
        sendLastPublished = config.get('pubsub#send_last_published_item',
                                       'never')
        if sendLastPublished == 'on_sub' and node.nodeType == 'leaf':
            entity = subscription.subscriber.userhostJID()
            d = self.getItems(node.nodeIdentifier, entity, 1)
            d.addCallback(notifyItem)
            d.addErrback(log.err)

        return subscription


    def unsubscribe(self, nodeIdentifier, subscriber, requestor):
        if subscriber.userhostJID() != requestor:
            return defer.fail(error.Forbidden())

        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(lambda node: node.removeSubscription(subscriber))
        return d


    def getSubscriptions(self, entity):
        return self.storage.getSubscriptions(entity)


    def supportsInstantNodes(self):
        return True


    def createNode(self, nodeIdentifier, requestor):
        if not nodeIdentifier:
            nodeIdentifier = 'generic/%s' % uuid.uuid4()

        nodeType = 'leaf'
        config = self.storage.getDefaultConfiguration(nodeType)
        config['pubsub#node_type'] = nodeType

        d = self.storage.createNode(nodeIdentifier, requestor, config)
        d.addCallback(lambda _: nodeIdentifier)
        return d


    def getDefaultConfiguration(self, nodeType):
        d = defer.succeed(self.storage.getDefaultConfiguration(nodeType))
        return d


    def getNodeConfiguration(self, nodeIdentifier):
        if not nodeIdentifier:
            return defer.fail(error.NoRootNode())

        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(lambda node: node.getConfiguration())

        return d


    def setNodeConfiguration(self, nodeIdentifier, options, requestor):
        if not nodeIdentifier:
            return defer.fail(error.NoRootNode())

        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(_getAffiliation, requestor)
        d.addCallback(self._doSetNodeConfiguration, options)
        return d


    def _doSetNodeConfiguration(self, result, options):
        node, affiliation = result

        if affiliation != 'owner':
            raise error.Forbidden()

        return node.setConfiguration(options)


    def getAffiliations(self, entity):
        return self.storage.getAffiliations(entity)


    def getItems(self, nodeIdentifier, requestor, maxItems=None,
                       itemIdentifiers=None):
        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(_getAffiliation, requestor)
        d.addCallback(self._doGetItems, maxItems, itemIdentifiers)
        return d


    def _doGetItems(self, result, maxItems, itemIdentifiers):
        node, affiliation = result

        if not ILeafNode.providedBy(node):
            return []

        if affiliation == 'outcast':
            raise error.Forbidden()

        if itemIdentifiers:
            return node.getItemsById(itemIdentifiers)
        else:
            return node.getItems(maxItems)


    def retractItem(self, nodeIdentifier, itemIdentifiers, requestor):
        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(_getAffiliation, requestor)
        d.addCallback(self._doRetract, itemIdentifiers)
        return d


    def _doRetract(self, result, itemIdentifiers):
        node, affiliation = result
        persistItems = node.getConfiguration()["pubsub#persist_items"]

        if affiliation not in ['owner', 'publisher']:
            raise error.Forbidden()

        if not persistItems:
            raise error.NodeNotPersistent()

        d = node.removeItems(itemIdentifiers)
        d.addCallback(self._doNotifyRetraction, node.nodeIdentifier)
        return d


    def _doNotifyRetraction(self, itemIdentifiers, nodeIdentifier):
        self.dispatch({'itemIdentifiers': itemIdentifiers,
                       'nodeIdentifier': nodeIdentifier },
                      '//event/pubsub/retract')


    def purgeNode(self, nodeIdentifier, requestor):
        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(_getAffiliation, requestor)
        d.addCallback(self._doPurge)
        return d


    def _doPurge(self, result):
        node, affiliation = result
        persistItems = node.getConfiguration()["pubsub#persist_items"]

        if affiliation != 'owner':
            raise error.Forbidden()

        if not persistItems:
            raise error.NodeNotPersistent()

        d = node.purge()
        d.addCallback(self._doNotifyPurge, node.nodeIdentifier)
        return d


    def _doNotifyPurge(self, result, nodeIdentifier):
        self.dispatch(nodeIdentifier, '//event/pubsub/purge')


    def registerPreDelete(self, preDeleteFn):
        self._callbackList.append(preDeleteFn)


    def getSubscribers(self, nodeIdentifier):
        def cb(subscriptions):
            return [subscription.subscriber for subscription in subscriptions]

        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(lambda node: node.getSubscriptions('subscribed'))
        d.addCallback(cb)
        return d


    def deleteNode(self, nodeIdentifier, requestor, redirectURI=None):
        d = self.storage.getNode(nodeIdentifier)
        d.addCallback(_getAffiliation, requestor)
        d.addCallback(self._doPreDelete, redirectURI)
        return d


    def _doPreDelete(self, result, redirectURI):
        node, affiliation = result

        if affiliation != 'owner':
            raise error.Forbidden()

        data = {'nodeIdentifier': node.nodeIdentifier,
                'redirectURI': redirectURI}

        d = defer.DeferredList([cb(data)
                                for cb in self._callbackList],
                               consumeErrors=1)
        d.addCallback(self._doDelete, node.nodeIdentifier)


    def _doDelete(self, result, nodeIdentifier):
        dl = []
        for succeeded, r in result:
            if succeeded and r:
                dl.extend(r)

        d = self.storage.deleteNode(nodeIdentifier)
        d.addCallback(self._doNotifyDelete, dl)

        return d


    def _doNotifyDelete(self, result, dl):
        for d in dl:
            d.callback(None)



class PubSubServiceFromBackend(PubSubService):
    """
    Adapts a backend to an xmpp publish-subscribe service.
    """

    implements(IDisco)

    _errorMap = {
        error.NodeNotFound: ('item-not-found', None, None),
        error.NodeExists: ('conflict', None, None),
        error.Forbidden: ('forbidden', None, None),
        error.ItemForbidden: ('bad-request', 'item-forbidden', None),
        error.ItemRequired: ('bad-request', 'item-required', None),
        error.NoInstantNodes: ('not-acceptable',
                               'unsupported',
                               'instant-nodes'),
        error.NotSubscribed: ('unexpected-request', 'not-subscribed', None),
        error.InvalidConfigurationOption: ('not-acceptable', None, None),
        error.InvalidConfigurationValue: ('not-acceptable', None, None),
        error.NodeNotPersistent: ('feature-not-implemented',
                                  'unsupported',
                                  'persistent-node'),
        error.NoRootNode: ('bad-request', None, None),
        error.NoCollections: ('feature-not-implemented',
                              'unsupported',
                              'collections'),
        error.NoPublishing: ('feature-not-implemented',
                             'unsupported',
                             'publish'),
    }

    def __init__(self, backend):
        PubSubService.__init__(self)

        self.backend = backend
        self.hideNodes = False

        self.pubSubFeatures = self._getPubSubFeatures()

        self.backend.registerNotifier(self._notify)
        self.backend.registerPreDelete(self._preDelete)


    def _getPubSubFeatures(self):
        features = [
            "config-node",
            "create-nodes",
            "delete-any",
            "delete-nodes",
            "item-ids",
            "meta-data",
            "publish",
            "purge-nodes",
            "retract-items",
            "retrieve-affiliations",
            "retrieve-default",
            "retrieve-items",
            "retrieve-subscriptions",
            "subscribe",
        ]

        if self.backend.supportsInstantNodes():
            features.append("instant-nodes")

        if self.backend.supportsOutcastAffiliation():
            features.append("outcast-affiliation")

        if self.backend.supportsPersistentItems():
            features.append("persistent-items")

        if self.backend.supportsPublisherAffiliation():
            features.append("publisher-affiliation")

        return features


    def _notify(self, data):
        items = data['items']
        nodeIdentifier = data['nodeIdentifier']
        if 'subscription' not in data:
            d = self.backend.getNotifications(nodeIdentifier, items)
        else:
            subscription = data['subscription']
            d = defer.succeed([(subscription.subscriber, [subscription],
                                items)])
        d.addCallback(lambda notifications: self.notifyPublish(self.serviceJID,
                                                               nodeIdentifier,
                                                               notifications))


    def _preDelete(self, data):
        nodeIdentifier = data['nodeIdentifier']
        redirectURI = data.get('redirectURI', None)
        d = self.backend.getSubscribers(nodeIdentifier)
        d.addCallback(lambda subscribers: self.notifyDelete(self.serviceJID,
                                                            nodeIdentifier,
                                                            subscribers,
                                                            redirectURI))
        return d


    def _mapErrors(self, failure):
        e = failure.trap(*self._errorMap.keys())

        condition, pubsubCondition, feature = self._errorMap[e]
        msg = failure.value.msg

        if pubsubCondition:
            exc = PubSubError(condition, pubsubCondition, feature, msg)
        else:
            exc = StanzaError(condition, text=msg)

        raise exc


    def getNodeInfo(self, requestor, service, nodeIdentifier):
        info = {}

        def saveType(result):
            info['type'] = result
            return nodeIdentifier

        def saveMetaData(result):
            info['meta-data'] = result
            return info

        def trapNotFound(failure):
            failure.trap(error.NodeNotFound)
            return info

        d = defer.succeed(nodeIdentifier)
        d.addCallback(self.backend.getNodeType)
        d.addCallback(saveType)
        d.addCallback(self.backend.getNodeMetaData)
        d.addCallback(saveMetaData)
        d.addErrback(trapNotFound)
        d.addErrback(self._mapErrors)
        return d


    def getNodes(self, requestor, service):
        if service.resource:
            return defer.succeed([])
        d = self.backend.getNodes()
        return d.addErrback(self._mapErrors)


    def publish(self, requestor, service, nodeIdentifier, items):
        d = self.backend.publish(nodeIdentifier, items, requestor)
        return d.addErrback(self._mapErrors)


    def subscribe(self, requestor, service, nodeIdentifier, subscriber):
        d = self.backend.subscribe(nodeIdentifier, subscriber, requestor)
        return d.addErrback(self._mapErrors)


    def unsubscribe(self, requestor, service, nodeIdentifier, subscriber):
        d = self.backend.unsubscribe(nodeIdentifier, subscriber, requestor)
        return d.addErrback(self._mapErrors)


    def subscriptions(self, requestor, service):
        d = self.backend.getSubscriptions(requestor)
        return d.addErrback(self._mapErrors)


    def affiliations(self, requestor, service):
        d = self.backend.getAffiliations(requestor)
        return d.addErrback(self._mapErrors)


    def create(self, requestor, service, nodeIdentifier):
        d = self.backend.createNode(nodeIdentifier, requestor)
        return d.addErrback(self._mapErrors)


    def getConfigurationOptions(self):
        return self.backend.nodeOptions


    def getDefaultConfiguration(self, requestor, service, nodeType):
        d = self.backend.getDefaultConfiguration(nodeType)
        return d.addErrback(self._mapErrors)


    def getConfiguration(self, requestor, service, nodeIdentifier):
        d = self.backend.getNodeConfiguration(nodeIdentifier)
        return d.addErrback(self._mapErrors)


    def setConfiguration(self, requestor, service, nodeIdentifier, options):
        d = self.backend.setNodeConfiguration(nodeIdentifier, options,
                                                requestor)
        return d.addErrback(self._mapErrors)


    def items(self, requestor, service, nodeIdentifier, maxItems,
                    itemIdentifiers):
        d = self.backend.getItems(nodeIdentifier, requestor, maxItems,
                                   itemIdentifiers)
        return d.addErrback(self._mapErrors)


    def retract(self, requestor, service, nodeIdentifier, itemIdentifiers):
        d = self.backend.retractItem(nodeIdentifier, itemIdentifiers,
                                      requestor)
        return d.addErrback(self._mapErrors)


    def purge(self, requestor, service, nodeIdentifier):
        d = self.backend.purgeNode(nodeIdentifier, requestor)
        return d.addErrback(self._mapErrors)


    def delete(self, requestor, service, nodeIdentifier):
        d = self.backend.deleteNode(nodeIdentifier, requestor)
        return d.addErrback(self._mapErrors)

components.registerAdapter(PubSubServiceFromBackend,
                           IBackendService,
                           IPubSubService)

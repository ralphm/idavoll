# -*- test-case-name: idavoll.test.test_backend -*-
#
# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

import uuid

from zope.interface import implements

from twisted.application import service
from twisted.python import components
from twisted.internet import defer, reactor
from twisted.words.protocols.jabber.error import StanzaError
from twisted.words.xish import domish, utility

from wokkel.iwokkel import IDisco, IPubSubService
from wokkel.pubsub import PubSubService, PubSubError

from idavoll import error, iidavoll
from idavoll.iidavoll import IBackendService

def _get_affiliation(node, entity):
    d = node.get_affiliation(entity)
    d.addCallback(lambda affiliation: (node, affiliation))
    return d


class BackendService(service.Service, utility.EventDispatcher):

    implements(iidavoll.IBackendService)

    options = {"pubsub#persist_items":
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
                       "on_sub": "When a new subscription is processed",
                       }
                  },
              }

    default_config = {"pubsub#persist_items": True,
                      "pubsub#deliver_payloads": True,
                      "pubsub#send_last_published_item": 'on_sub',
                     }

    def __init__(self, storage):
        utility.EventDispatcher.__init__(self)
        self.storage = storage
        self._callback_list = []

    def supports_publisher_affiliation(self):
        return True

    def supports_outcast_affiliation(self):
        return True

    def supports_persistent_items(self):
        return True

    def get_node_type(self, node_id):
        d = self.storage.get_node(node_id)
        d.addCallback(lambda node: node.get_type())
        return d

    def get_nodes(self):
        return self.storage.get_node_ids()

    def get_node_meta_data(self, node_id):
        d = self.storage.get_node(node_id)
        d.addCallback(lambda node: node.get_meta_data())
        d.addCallback(self._make_meta_data)
        return d

    def _make_meta_data(self, meta_data):
        options = []
        for key, value in meta_data.iteritems():
            if self.options.has_key(key):
                option = {"var": key}
                option.update(self.options[key])
                option["value"] = value
                options.append(option)

        return options

    def _check_auth(self, node, requestor):
        def check(affiliation, node):
            if affiliation not in ['owner', 'publisher']:
                raise error.Forbidden()
            return node

        d = node.get_affiliation(requestor)
        d.addCallback(check, node)
        return d

    def publish(self, node_id, items, requestor):
        d = self.storage.get_node(node_id)
        d.addCallback(self._check_auth, requestor)
        d.addCallback(self._do_publish, items, requestor)
        return d

    def _do_publish(self, node, items, requestor):
        configuration = node.get_configuration()
        persist_items = configuration["pubsub#persist_items"]
        deliver_payloads = configuration["pubsub#deliver_payloads"]

        if items and not persist_items and not deliver_payloads:
            raise error.ItemForbidden()
        elif not items and (persist_items or deliver_payloads):
            raise error.ItemRequired()

        if persist_items or deliver_payloads:
            for item in items:
                if not item.getAttribute("id"):
                    item["id"] = str(uuid.uuid4())

        if persist_items:
            d = node.store_items(items, requestor)
        else:
            d = defer.succeed(None)

        d.addCallback(self._do_notify, node.id, items, deliver_payloads)
        return d

    def _do_notify(self, result, node_id, items, deliver_payloads):
        if items and not deliver_payloads:
            for item in items:
                item.children = []

        self.dispatch({'items': items, 'node_id': node_id},
                      '//event/pubsub/notify')

    def get_notification_list(self, node_id, items):
        d = self.storage.get_node(node_id)
        d.addCallback(lambda node: node.get_subscribers())
        d.addCallback(self._magic_filter, node_id, items)
        return d

    def _magic_filter(self, subscribers, node_id, items):
        list = []
        for subscriber in subscribers:
            list.append((subscriber, items))
        return list

    def register_notifier(self, observerfn, *args, **kwargs):
        self.addObserver('//event/pubsub/notify', observerfn, *args, **kwargs)

    def subscribe(self, node_id, subscriber, requestor):
        subscriber_entity = subscriber.userhostJID()
        if subscriber_entity != requestor:
            return defer.fail(error.Forbidden())

        d = self.storage.get_node(node_id)
        d.addCallback(_get_affiliation, subscriber_entity)
        d.addCallback(self._do_subscribe, subscriber)
        return d

    def _do_subscribe(self, result, subscriber):
        node, affiliation = result

        if affiliation == 'outcast':
            raise error.Forbidden()

        d = node.add_subscription(subscriber, 'subscribed')
        d.addCallback(lambda _: self._send_last_published(node, subscriber))
        d.addCallback(lambda _: 'subscribed')
        d.addErrback(self._get_subscription, node, subscriber)
        d.addCallback(self._return_subscription, node.id)
        return d

    def _get_subscription(self, failure, node, subscriber):
        failure.trap(error.SubscriptionExists)
        return node.get_subscription(subscriber)

    def _return_subscription(self, result, node_id):
        return node_id, result

    def _send_last_published(self, node, subscriber):
        class StringParser(object):
            def __init__(self):
                self.elementStream = domish.elementStream()
                self.elementStream.DocumentStartEvent = self.docStart
                self.elementStream.ElementEvent = self.elem
                self.elementStream.DocumentEndEvent = self.docEnd

            def docStart(self, elem):
                self.document = elem

            def elem(self, elem):
                self.document.addChild(elem)

            def docEnd(self):
                pass

            def parse(self, string):
                self.elementStream.parse(string)
                return self.document

        def notify_item(result):
            if not result:
                return

            items = [domish.SerializedXML(item) for item in result]

            reactor.callLater(0, self.dispatch, {'items': items,
                                                 'node_id': node.id,
                                                 'subscriber': subscriber},
                                                 '//event/pubsub/notify')

        config = node.get_configuration()
        if config.get("pubsub#send_last_published_item", 'never') != 'on_sub':
            return

        d = self.get_items(node.id, subscriber.userhostJID(), 1)
        d.addCallback(notify_item)

    def unsubscribe(self, node_id, subscriber, requestor):
        if subscriber.userhostJID() != requestor:
            return defer.fail(error.Forbidden())

        d = self.storage.get_node(node_id)
        d.addCallback(lambda node: node.remove_subscription(subscriber))
        return d

    def get_subscriptions(self, entity):
        return self.storage.get_subscriptions(entity)

    def supports_instant_nodes(self):
        return True

    def create_node(self, node_id, requestor):
        if not node_id:
            node_id = 'generic/%s' % uuid.uuid4()
        d = self.storage.create_node(node_id, requestor)
        d.addCallback(lambda _: node_id)
        return d

    def get_default_configuration(self):
        d = defer.succeed(self.default_config)
        d.addCallback(self._make_config)
        return d

    def get_node_configuration(self, node_id):
        if not node_id:
            raise error.NoRootNode()

        d = self.storage.get_node(node_id)
        d.addCallback(lambda node: node.get_configuration())

        d.addCallback(self._make_config)
        return d

    def _make_config(self, config):
        options = []
        for key, value in self.options.iteritems():
            option = {"var": key}
            option.update(value)
            if config.has_key(key):
                option["value"] = config[key]
            options.append(option)

        return options

    def set_node_configuration(self, node_id, options, requestor):
        if not node_id:
            raise error.NoRootNode()

        for key, value in options.iteritems():
            if not self.options.has_key(key):
                raise error.InvalidConfigurationOption()
            if self.options[key]["type"] == 'boolean':
                try:
                    options[key] = bool(int(value))
                except ValueError:
                    raise error.InvalidConfigurationValue()

        d = self.storage.get_node(node_id)
        d.addCallback(_get_affiliation, requestor)
        d.addCallback(self._do_set_node_configuration, options)
        return d

    def _do_set_node_configuration(self, result, options):
        node, affiliation = result

        if affiliation != 'owner':
            raise error.Forbidden()

        return node.set_configuration(options)

    def get_affiliations(self, entity):
        return self.storage.get_affiliations(entity)

    def get_items(self, node_id, requestor, max_items=None, item_ids=[]):
        d = self.storage.get_node(node_id)
        d.addCallback(_get_affiliation, requestor)
        d.addCallback(self._do_get_items, max_items, item_ids)
        return d

    def _do_get_items(self, result, max_items, item_ids):
        node, affiliation = result

        if affiliation == 'outcast':
            raise error.Forbidden()

        if item_ids:
            return node.get_items_by_id(item_ids)
        else:
            return node.get_items(max_items)

    def retract_item(self, node_id, item_ids, requestor):
        d = self.storage.get_node(node_id)
        d.addCallback(_get_affiliation, requestor)
        d.addCallback(self._do_retract, item_ids)
        return d

    def _do_retract(self, result, item_ids):
        node, affiliation = result
        persist_items = node.get_configuration()["pubsub#persist_items"]

        if affiliation not in ['owner', 'publisher']:
            raise error.Forbidden()

        if not persist_items:
            raise error.NodeNotPersistent()

        d = node.remove_items(item_ids)
        d.addCallback(self._do_notify_retraction, node.id)
        return d

    def _do_notify_retraction(self, item_ids, node_id):
        self.dispatch({ 'item_ids': item_ids, 'node_id': node_id },
                             '//event/pubsub/retract')

    def purge_node(self, node_id, requestor):
        d = self.storage.get_node(node_id)
        d.addCallback(_get_affiliation, requestor)
        d.addCallback(self._do_purge)
        return d

    def _do_purge(self, result):
        node, affiliation = result
        persist_items = node.get_configuration()["pubsub#persist_items"]

        if affiliation != 'owner':
            raise error.Forbidden()

        if not persist_items:
            raise error.NodeNotPersistent()

        d = node.purge()
        d.addCallback(self._do_notify_purge, node.id)
        return d

    def _do_notify_purge(self, result, node_id):
        self.dispatch(node_id, '//event/pubsub/purge')

    def register_pre_delete(self, pre_delete_fn):
        self._callback_list.append(pre_delete_fn)

    def get_subscribers(self, node_id):
        d = self.storage.get_node(node_id)
        d.addCallback(lambda node: node.get_subscribers())
        return d

    def delete_node(self, node_id, requestor):
        d = self.storage.get_node(node_id)
        d.addCallback(_get_affiliation, requestor)
        d.addCallback(self._do_pre_delete)
        return d

    def _do_pre_delete(self, result):
        node, affiliation = result

        if affiliation != 'owner':
            raise error.Forbidden()

        d = defer.DeferredList([cb(node.id) for cb in self._callback_list],
                               consumeErrors=1)
        d.addCallback(self._do_delete, node.id)

    def _do_delete(self, result, node_id):
        dl = []
        for succeeded, r in result:
            if succeeded and r:
                dl.extend(r)

        d = self.storage.delete_node(node_id)
        d.addCallback(self._do_notify_delete, dl)

        return d

    def _do_notify_delete(self, result, dl):
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
    }

    def __init__(self, backend):
        PubSubService.__init__(self)

        self.backend = backend
        self.hideNodes = False

        self.pubSubFeatures = self._getPubSubFeatures()

        self.backend.register_notifier(self._notify)
        self.backend.register_pre_delete(self._pre_delete)

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

        if self.backend.supports_instant_nodes():
            features.append("instant-nodes")

        if self.backend.supports_outcast_affiliation():
            features.append("outcast-affiliation")

        if self.backend.supports_persistent_items():
            features.append("persistent-items")

        if self.backend.supports_publisher_affiliation():
            features.append("publisher-affiliation")

        return features

    def _notify(self, data):
        items = data['items']
        nodeIdentifier = data['node_id']
        if 'subscriber' not in data:
            d = self.backend.get_notification_list(nodeIdentifier, items)
        else:
            d = defer.succeed([(data['subscriber'], items)])
        d.addCallback(lambda notifications: self.notifyPublish(self.serviceJID,
                                                               nodeIdentifier,
                                                               notifications))

    def _pre_delete(self, nodeIdentifier):
        d = self.backend.get_subscribers(nodeIdentifier)
        d.addCallback(lambda subscribers: self.notifyDelete(self.serviceJID,
                                                            nodeIdentifier,
                                                            subscribers))
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

        d = defer.succeed(nodeIdentifier)
        d.addCallback(self.backend.get_node_type)
        d.addCallback(saveType)
        d.addCallback(self.backend.get_node_meta_data)
        d.addCallback(saveMetaData)
        d.addErrback(self._mapErrors)
        return d

    def getNodes(self, requestor, service):
        if service.resource:
            return defer.succeed([])
        d = self.backend.get_nodes()
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
        d = self.backend.get_subscriptions(requestor)
        return d.addErrback(self._mapErrors)

    def affiliations(self, requestor, service):
        d = self.backend.get_affiliations(requestor)
        return d.addErrback(self._mapErrors)

    def create(self, requestor, service, nodeIdentifier):
        d = self.backend.create_node(nodeIdentifier, requestor)
        return d.addErrback(self._mapErrors)

    def getDefaultConfiguration(self, requestor, service):
        d = self.backend.get_default_configuration()
        return d.addErrback(self._mapErrors)

    def getConfiguration(self, requestor, service, nodeIdentifier):
        d = self.backend.get_node_configuration(nodeIdentifier)
        return d.addErrback(self._mapErrors)

    def setConfiguration(self, requestor, service, nodeIdentifier, options):
        d = self.backend.set_node_configuration(nodeIdentifier, options,
                                                requestor)
        return d.addErrback(self._mapErrors)

    def items(self, requestor, service, nodeIdentifier, maxItems, itemIdentifiers):
        d = self.backend.get_items(nodeIdentifier, requestor, maxItems,
                                   itemIdentifiers)
        return d.addErrback(self._mapErrors)

    def retract(self, requestor, service, nodeIdentifier, itemIdentifiers):
        d = self.backend.retract_item(nodeIdentifier, itemIdentifiers,
                                      requestor)
        return d.addErrback(self._mapErrors)

    def purge(self, requestor, service, nodeIdentifier):
        d = self.backend.purge_node(nodeIdentifier, requestor)
        return d.addErrback(self._mapErrors)

    def delete(self, requestor, service, nodeIdentifier):
        d = self.backend.delete_node(nodeIdentifier, requestor)
        return d.addErrback(self._mapErrors)

components.registerAdapter(PubSubServiceFromBackend,
                           IBackendService,
                           IPubSubService)

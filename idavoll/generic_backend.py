import sha
import time
import uuid
from twisted.words.protocols.jabber import jid
from twisted.words.xish import utility
from twisted.application import service
from twisted.internet import defer
from zope.interface import implements
import backend, storage

def _get_affiliation(node, entity):
    d = node.get_affiliation(entity)
    d.addCallback(lambda affiliation: (node, affiliation))
    return d

class BackendService(service.MultiService, utility.EventDispatcher):

    implements(backend.IBackendService)

    options = {"pubsub#persist_items":
                  {"type": "boolean",
                   "label": "Persist items to storage"},
               "pubsub#deliver_payloads":
                  {"type": "boolean",
                   "label": "Deliver payloads with event notifications"},
              }

    default_config = {"pubsub#persist_items": True,
                      "pubsub#deliver_payloads": True,
                     }

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

class PublishService(service.Service):
    
    implements(backend.IPublishService)

    def _check_auth(self, node, requestor):
        def check(affiliation, node):
            if affiliation not in ['owner', 'publisher']:
                raise backend.NotAuthorized
            return node

        d = node.get_affiliation(requestor)
        d.addCallback(check, node)
        return d

    def publish(self, node_id, items, requestor):
        d = self.parent.storage.get_node(node_id)
        d.addCallback(self._check_auth, requestor)
        d.addCallback(self._do_publish, items, requestor)
        return d

    def _do_publish(self, node, items, requestor):
        configuration = node.get_configuration()
        persist_items = configuration["pubsub#persist_items"]
        deliver_payloads = configuration["pubsub#deliver_payloads"]
        
        if items and not persist_items and not deliver_payloads:
            raise backend.NoPayloadAllowed
        elif not items and (persist_items or deliver_payloads):
            raise backend.PayloadExpected

        if persist_items or deliver_payloads:
            for item in items:
                if not item.getAttribute("id"):
                    item["id"] = uuid.generate() 

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

        self.parent.dispatch({ 'items': items, 'node_id': node_id },
                             '//event/pubsub/notify')

class NotificationService(service.Service):

    implements(backend.INotificationService)

    def get_notification_list(self, node_id, items):
        d = self.parent.storage.get_node(node_id)
        d.addCallback(lambda node: node.get_subscribers())
        d.addCallback(self._magic_filter, node_id, items)
        return d

    def _magic_filter(self, subscribers, node_id, items):
        list = []
        for subscriber in subscribers:
            list.append((subscriber, items))
        return list

    def register_notifier(self, observerfn, *args, **kwargs):
        self.parent.addObserver('//event/pubsub/notify', observerfn,
                                *args, **kwargs)

class SubscriptionService(service.Service):

    implements(backend.ISubscriptionService)

    def subscribe(self, node_id, subscriber, requestor):
        subscriber_entity = subscriber.userhostJID()
        if subscriber_entity != requestor:
            return defer.fail(backend.NotAuthorized())

        d = self.parent.storage.get_node(node_id)
        d.addCallback(_get_affiliation, subscriber_entity)
        d.addCallback(self._do_subscribe, subscriber)
        return d

    def _do_subscribe(self, result, subscriber):
        node, affiliation = result

        if affiliation == 'outcast':
            raise backend.NotAuthorized

        d = node.add_subscription(subscriber, 'subscribed')
        d.addCallback(lambda _: 'subscribed')
        d.addErrback(self._get_subscription, node, subscriber)
        d.addCallback(self._return_subscription, affiliation, node.id)
        return d

    def _get_subscription(self, failure, node, subscriber):
        failure.trap(storage.SubscriptionExists)
        return node.get_subscription(subscriber)

    def _return_subscription(self, result, affiliation, node_id):
        return {'affiliation': affiliation,
                'node': node_id,
                'state': result}

    def unsubscribe(self, node_id, subscriber, requestor):
        if subscriber.userhostJID() != requestor:
            raise backend.NotAuthorized

        d = self.parent.storage.get_node(node_id)
        d.addCallback(lambda node: node.remove_subscription(subscriber))
        return d

class NodeCreationService(service.Service):

    implements(backend.INodeCreationService)

    def supports_instant_nodes(self):
        return True

    def create_node(self, node_id, requestor):
        if not node_id:
            node_id = 'generic/%s' % uuid.generate() 
        d = self.parent.storage.create_node(node_id, requestor)
        d.addCallback(lambda _: node_id)
        return d

    def get_node_configuration(self, node_id):
        if node_id:
            d = self.parent.storage.get_node(node_id)
            d.addCallback(lambda node: node.get_configuration())
        else:
            # XXX: this is disabled in pubsub.py
            d = defer.succeed(self.parent.default_config)

        d.addCallback(self._make_config)
        return d

    def _make_config(self, config):
        options = []
        for key, value in self.parent.options.iteritems():
            option = {"var": key}
            option.update(value)
            if config.has_key(key):
                option["value"] = config[key]
            options.append(option)

        return options

    def set_node_configuration(self, node_id, options, requestor):
        for key, value in options.iteritems():
            if not self.parent.options.has_key(key):
                raise backend.InvalidConfigurationOption
            if self.parent.options[key]["type"] == 'boolean':
                try:
                    options[key] = bool(int(value))
                except ValueError:
                    raise backend.InvalidConfigurationValue

        d = self.parent.storage.get_node(node_id)
        d.addCallback(_get_affiliation, requestor)
        d.addCallback(self._do_set_node_configuration, options)
        return d

    def _do_set_node_configuration(self, result, options):
        node, affiliation = result

        if affiliation != 'owner':
            raise backend.NotAuthorized

        return node.set_configuration(options)

class AffiliationsService(service.Service):

    implements(backend.IAffiliationsService)

    def get_affiliations(self, entity):
        d1 = self.parent.storage.get_affiliations(entity)
        d2 = self.parent.storage.get_subscriptions(entity)
        d = defer.DeferredList([d1, d2], fireOnOneErrback=1, consumeErrors=1)
        d.addErrback(lambda x: x.value[0])
        d.addCallback(self._affiliations_result, entity)
        return d

    def _affiliations_result(self, result, entity):
        affiliations = result[0][1]
        subscriptions = result[1][1]

        new_affiliations = {}

        for node, affiliation in affiliations:
            new_affiliations[(node, entity.full())] = {'node': node,
                                                'jid': entity,
                                                'affiliation': affiliation,
                                                'subscription': None
                                               }

        for node, subscriber, subscription in subscriptions:
            key = node, subscriber.full()
            if new_affiliations.has_key(key):
                new_affiliations[key]['subscription'] = subscription
            else:
                new_affiliations[key] = {'node': node,
                                         'jid': subscriber,
                                         'affiliation': None,
                                         'subscription': subscription}

        return new_affiliations.values()

class ItemRetrievalService(service.Service):

    implements(backend.IItemRetrievalService)

    def get_items(self, node_id, requestor, max_items=None, item_ids=[]):
        d = self.parent.storage.get_node(node_id)
        d.addCallback(self._is_subscribed, requestor)
        d.addCallback(self._do_get_items, max_items, item_ids)
        return d

    def _is_subscribed(self, node, subscriber):
        d = node.is_subscribed(subscriber)
        d.addCallback(lambda subscribed: (node, subscribed))
        return d

    def _do_get_items(self, result, max_items, item_ids):
        node, subscribed = result

        if not subscribed:
            raise backend.NotAuthorized

        if item_ids:
            return node.get_items_by_id(item_ids)
        else:
            return node.get_items(max_items)

class RetractionService(service.Service):

    implements(backend.IRetractionService)
                                                                                
    def retract_item(self, node_id, item_ids, requestor):
        d = self.parent.storage.get_node(node_id)
        d.addCallback(_get_affiliation, requestor)
        d.addCallback(self._do_retract, item_ids)
        return d
                                                                                
    def _do_retract(self, result, item_ids):
        node, affiliation = result
        persist_items = node.get_configuration()["pubsub#persist_items"]
                                                                                
        if affiliation not in ['owner', 'publisher']:
            raise backend.NotAuthorized
                                                                                
        if not persist_items:
            raise backend.NodeNotPersistent
                                                                                
        d = node.remove_items(item_ids)
        d.addCallback(self._do_notify_retraction, node.id)
        return d
                                                                                
    def _do_notify_retraction(self, item_ids, node_id):
        self.parent.dispatch({ 'item_ids': item_ids, 'node_id': node_id },
                             '//event/pubsub/retract')
                                                                                
    def purge_node(self, node_id, requestor):
        d = self.parent.storage.get_node(node_id)
        d.addCallback(_get_affiliation, requestor)
        d.addCallback(self._do_purge)
        return d
    
    def _do_purge(self, result):
        node, affiliation = result
        persist_items = node.get_configuration()["pubsub#persist_items"]
                                                                                
        if affiliation != 'owner':
            raise backend.NotAuthorized
                                                                                
        if not persist_items:
            raise backend.NodeNotPersistent
                                                                                
        d = node.purge()
        d.addCallback(self._do_notify_purge, node.id)
        return d
    
    def _do_notify_purge(self, result, node_id):
        self.parent.dispatch(node_id, '//event/pubsub/purge')

class NodeDeletionService(service.Service):

    implements(backend.INodeDeletionService)

    def __init__(self):
        self._callback_list = []

    def register_pre_delete(self, pre_delete_fn):
        self._callback_list.append(pre_delete_fn)

    def get_subscribers(self, node_id):
        d = self.parent.storage.get_node(node_id)
        d.addCallback(lambda node: node.get_subscribers())
        return d

    def delete_node(self, node_id, requestor):
        d = self.parent.storage.get_node(node_id)
        d.addCallback(_get_affiliation, requestor)
        d.addCallback(self._do_pre_delete)
        return d
    
    def _do_pre_delete(self, result):
        node, affiliation = result
                                                                                
        if affiliation != 'owner':
            raise backend.NotAuthorized

        d = defer.DeferredList([cb(node.id) for cb in self._callback_list],
                               consumeErrors=1)
        d.addCallback(self._do_delete, node.id)

    def _do_delete(self, result, node_id):
        dl = []
        for succeeded, r in result:
            if succeeded and r:
                dl.extend(r)

        d = self.parent.storage.delete_node(node_id)
        d.addCallback(self._do_notify_delete, dl)

        return d
    
    def _do_notify_delete(self, result, dl):
        for d in dl:
            d.callback(None)

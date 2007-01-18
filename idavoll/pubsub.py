# Copyright (c) 2003-2006 Ralph Meijer
# See LICENSE for details.

from zope.interface import implements

from twisted.words.protocols.jabber import component, jid, error
from twisted.words.xish import domish
from twisted.python import components
from twisted.internet import defer

import backend
import storage
import disco
import data_form

try:
    from twisted.words.protocols.jabber.ijabber import IService
except ImportError:
    from twisted.words.protocols.jabber.component import IService

if issubclass(domish.SerializedXML, str):
    # Work around bug # in twisted Xish
    class SerializedXML(unicode):
        """ Marker class for pre-serialized XML in the DOM. """

    domish.SerializedXML = SerializedXML

NS_COMPONENT = 'jabber:component:accept'
NS_PUBSUB = 'http://jabber.org/protocol/pubsub'
NS_PUBSUB_EVENT = NS_PUBSUB + '#event'
NS_PUBSUB_ERRORS = NS_PUBSUB + '#errors'
NS_PUBSUB_OWNER = NS_PUBSUB + "#owner"

IQ_GET = '/iq[@type="get"]'
IQ_SET = '/iq[@type="set"]'
PUBSUB_ELEMENT = '/pubsub[@xmlns="' + NS_PUBSUB + '"]'
PUBSUB_OWNER_ELEMENT = '/pubsub[@xmlns="' + NS_PUBSUB_OWNER + '"]'
PUBSUB_GET = IQ_GET + PUBSUB_ELEMENT
PUBSUB_SET = IQ_SET + PUBSUB_ELEMENT
PUBSUB_OWNER_GET = IQ_GET + PUBSUB_OWNER_ELEMENT
PUBSUB_OWNER_SET = IQ_SET + PUBSUB_OWNER_ELEMENT
PUBSUB_CREATE = PUBSUB_SET + '/create'
PUBSUB_PUBLISH = PUBSUB_SET + '/publish'
PUBSUB_SUBSCRIBE = PUBSUB_SET + '/subscribe'
PUBSUB_UNSUBSCRIBE = PUBSUB_SET + '/unsubscribe'
PUBSUB_OPTIONS_GET = PUBSUB_GET + '/options'
PUBSUB_OPTIONS_SET = PUBSUB_SET + '/options'
PUBSUB_DEFAULT = PUBSUB_OWNER_GET + '/default'
PUBSUB_CONFIGURE_GET = PUBSUB_OWNER_GET + '/configure'
PUBSUB_CONFIGURE_SET = PUBSUB_OWNER_SET + '/configure'
PUBSUB_SUBSCRIPTIONS = PUBSUB_GET + '/subscriptions'
PUBSUB_AFFILIATIONS = PUBSUB_GET + '/affiliations'
PUBSUB_ITEMS = PUBSUB_GET + '/items'
PUBSUB_RETRACT = PUBSUB_SET + '/retract'
PUBSUB_PURGE = PUBSUB_OWNER_SET + '/purge'
PUBSUB_DELETE = PUBSUB_OWNER_SET + '/delete'

class BadRequest(error.StanzaError):
    def __init__(self):
        error.StanzaError.__init__(self, 'bad-request')

class PubSubError(error.StanzaError):
    def __init__(self, condition, pubsubCondition, feature=None, text=None):
        appCondition = domish.Element((NS_PUBSUB_ERRORS, pubsubCondition))
        if feature:
            appCondition['feature'] = feature
        error.StanzaError.__init__(self, condition,
                                         text=text, 
                                         appCondition=appCondition)

class OptionsUnavailable(PubSubError):
    def __init__(self):
        PubSubError.__init__(self, 'feature-not-implemented',
                                   'unsupported',
                                   'subscription-options-unavailable')

error_map = {
    storage.NodeNotFound: ('item-not-found', None, None),
    storage.NodeExists: ('conflict', None, None),
    storage.SubscriptionNotFound: ('not-authorized', 'not-subscribed', None),
    backend.Forbidden: ('forbidden', None, None),
    backend.ItemForbidden: ('bad-request', 'item-forbidden', None),
    backend.ItemRequired: ('bad-request', 'item-required', None),
    backend.NoInstantNodes: ('not-acceptable', 'unsupported', 'instant-nodes'),
    backend.NotSubscribed: ('not-authorized', 'not-subscribed', None),
    backend.InvalidConfigurationOption: ('not-acceptable', None, None),
    backend.InvalidConfigurationValue: ('not-acceptable', None, None),
    backend.NodeNotPersistent: ('feature-not-implemented', 'unsupported',
                                                           'persistent-node'),
    backend.NoRootNode: ('bad-request', None, None),
}

class Service(component.Service):

    implements(IService)

    def __init__(self, backend):
        self.backend = backend

    def error(self, failure, iq):
        try: 
            e = failure.trap(error.StanzaError, *error_map.keys())
        except:
            failure.printBriefTraceback()
            return error.StanzaError('internal-server-error').toResponse(iq)
        else:
            if e == error.StanzaError:
                exc = failure.value
            else:
                condition, pubsubCondition, feature = error_map[e]
                msg = failure.value.msg

                if pubsubCondition:
                    exc = PubSubError(condition, pubsubCondition, feature, msg)
                else:
                    exc = error.StanzaError(condition, text=msg)

            return exc.toResponse(iq)
    
    def success(self, result, iq):
        iq.swapAttributeValues("to", "from")
        iq["type"] = 'result'
        iq.children = []
        if result:
            for child in result:
                iq.addChild(child)

        return iq

    def handler_wrapper(self, handler, iq):
        try:
            d = handler(iq)
        except:
            d = defer.fail()

        d.addCallback(self.success, iq)
        d.addErrback(self.error, iq)
        d.addCallback(self.send)
        iq.handled = True

class ComponentServiceFromService(Service):

    def __init__(self, backend):
        Service.__init__(self, backend)
        self.hide_nodes = False

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Identity('pubsub', 'generic',
                                       'Generic Pubsub Service'))

            info.append(disco.Feature(NS_PUBSUB + "#meta-data"))

            if self.backend.supports_outcast_affiliation():
                info.append(disco.Feature(NS_PUBSUB + "#outcast-affiliation"))

            if self.backend.supports_persistent_items():
                info.append(disco.Feature(NS_PUBSUB + "#persistent-items"))

            if self.backend.supports_publisher_affiliation():
                info.append(disco.Feature(NS_PUBSUB + "#publisher-affiliation"))

            return defer.succeed(info)
        else:
            def trap_not_found(result):
                result.trap(storage.NodeNotFound)
                return []

            d = self.backend.get_node_type(node)
            d.addCallback(self._add_identity, [], node)
            d.addErrback(trap_not_found)
            return d

    def _add_identity(self, node_type, result_list, node):
        result_list.append(disco.Identity('pubsub', node_type))
        d = self.backend.get_node_meta_data(node)
        d.addCallback(self._add_meta_data, node_type, result_list)
        return d

    def _add_meta_data(self, meta_data, node_type, result_list):
        form = data_form.Form(type="result",
                              form_type=NS_PUBSUB + "#meta-data")

        for meta_datum in meta_data:
            try:
                del meta_datum['options']
            except KeyError:
                pass
            
            form.add_field(**meta_datum)

        form.add_field("text-single",
                       "pubsub#node_type",
                       "The type of node (collection or leaf)",
                       node_type)
        result_list.append(form)
        return result_list

    def get_disco_items(self, node):
        if node or self.hide_nodes:
            return defer.succeed([])
        
        d = self.backend.get_nodes()
        d.addCallback(lambda nodes: [disco.Item(self.parent.jabberId, node)
                                    for node in nodes])
        return d

components.registerAdapter(ComponentServiceFromService,
                           backend.IBackendService,
                           IService)

class ComponentServiceFromNotificationService(Service):

    def componentConnected(self, xmlstream):
        self.backend.register_notifier(self.notify)
        
    def notify(self, object):
        node_id = object["node_id"]
        items = object["items"]
        d = self.backend.get_notification_list(node_id, items)
        d.addCallback(self._notify, node_id)

    def _notify(self, list, node_id):
        for recipient, items in list:
            self._notify_recipient(recipient, node_id, items)

    def _notify_recipient(self, recipient, node_id, itemlist):
        message = domish.Element((NS_COMPONENT, "message"))
        message["from"] = self.parent.jabberId
        message["to"] = recipient.full()
        event = message.addElement((NS_PUBSUB_EVENT, "event"))
        items = event.addElement("items")
        items["node"] = node_id
        items.children.extend(itemlist)
        self.send(message)

components.registerAdapter(ComponentServiceFromNotificationService,
                           backend.INotificationService,
                           IService)

class ComponentServiceFromPublishService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_PUBLISH, self.onPublish)

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + "#item-ids"))

        return defer.succeed(info)

    def onPublish(self, iq):
        self.handler_wrapper(self._onPublish, iq)

    def _onPublish(self, iq):
        try:
            node = iq.pubsub.publish["node"]
        except KeyError:
            raise BadRequest

        items = []
        for child in iq.pubsub.publish.children:
            if child.__class__ == domish.Element and child.name == 'item':
                items.append(child)

        return self.backend.publish(node, items,
                                    jid.internJID(iq["from"]).userhostJID())

components.registerAdapter(ComponentServiceFromPublishService,
                           backend.IPublishService,
                           IService)

class ComponentServiceFromSubscriptionService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_SUBSCRIBE, self.onSubscribe)
        xmlstream.addObserver(PUBSUB_UNSUBSCRIBE, self.onUnsubscribe)
        xmlstream.addObserver(PUBSUB_OPTIONS_GET, self.onOptionsGet)
        xmlstream.addObserver(PUBSUB_OPTIONS_SET, self.onOptionsSet)
        xmlstream.addObserver(PUBSUB_SUBSCRIPTIONS, self.onSubscriptions)
    
    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + '#subscribe'))
            info.append(disco.Feature(NS_PUBSUB + '#retrieve-subscriptions'))

        return defer.succeed(info)

    def onSubscribe(self, iq):
        self.handler_wrapper(self._onSubscribe, iq)

    def _onSubscribe(self, iq):
        try:
            node_id = iq.pubsub.subscribe["node"]
            subscriber = jid.internJID(iq.pubsub.subscribe["jid"])
        except KeyError:
            raise BadRequest

        requestor = jid.internJID(iq["from"]).userhostJID()
        d = self.backend.subscribe(node_id, subscriber, requestor)
        d.addCallback(self.return_subscription, subscriber)
        return d

    def return_subscription(self, result, subscriber):
        node, state = result

        reply = domish.Element((NS_PUBSUB, "pubsub"))
        subscription = reply.addElement("subscription")
        subscription["node"] = node
        subscription["jid"] = subscriber.full()
        subscription["subscription"] = state
        return [reply]

    def onUnsubscribe(self, iq):
        self.handler_wrapper(self._onUnsubscribe, iq)

    def _onUnsubscribe(self, iq):
        try:
            node_id = iq.pubsub.unsubscribe["node"]
            subscriber = jid.internJID(iq.pubsub.unsubscribe["jid"])
        except KeyError:
            raise BadRequest

        requestor = jid.internJID(iq["from"]).userhostJID()
        return self.backend.unsubscribe(node_id, subscriber, requestor)

    def onOptionsGet(self, iq):
        self.handler_wrapper(self._onOptionsGet, iq)

    def _onOptionsGet(self, iq):
        raise OptionsUnavailable

    def onOptionsSet(self, iq):
        self.handler_wrapper(self._onOptionsSet, iq)

    def _onOptionsSet(self, iq):
        raise OptionsUnavailable

    def onSubscriptions(self, iq):
        self.handler_wrapper(self._onSubscriptions, iq)

    def _onSubscriptions(self, iq):
        entity = jid.internJID(iq["from"]).userhostJID()
        d = self.backend.get_subscriptions(entity)
        d.addCallback(self._return_subscriptions_response, iq)
        return d

    def _return_subscriptions_response(self, result, iq):
        reply = domish.Element((NS_PUBSUB, 'pubsub'))
        subscriptions = reply.addElement('subscriptions')
        for node, subscriber, state in result:
            item = subscriptions.addElement('subscription')
            item['node'] = node
            item['jid'] = subscriber.full()
            item['subscription'] = state
        return [reply]

components.registerAdapter(ComponentServiceFromSubscriptionService,
                           backend.ISubscriptionService,
                           IService)

class ComponentServiceFromNodeCreationService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_CREATE, self.onCreate)
        xmlstream.addObserver(PUBSUB_DEFAULT, self.onDefault)
        xmlstream.addObserver(PUBSUB_CONFIGURE_GET, self.onConfigureGet)
        xmlstream.addObserver(PUBSUB_CONFIGURE_SET, self.onConfigureSet)

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + "#create-nodes"))
            info.append(disco.Feature(NS_PUBSUB + "#config-node"))
            info.append(disco.Feature(NS_PUBSUB + "#retrieve-default"))

            if self.backend.supports_instant_nodes():
                info.append(disco.Feature(NS_PUBSUB + "#instant-nodes"))

        return defer.succeed(info)

    def onCreate(self, iq):
        print "onCreate"
        self.handler_wrapper(self._onCreate, iq)

    def _onCreate(self, iq):
        node = iq.pubsub.create.getAttribute("node")

        owner = jid.internJID(iq["from"]).userhostJID()

        d = self.backend.create_node(node, owner)
        d.addCallback(self._return_create_response, iq)
        return d

    def _return_create_response(self, result, iq):
        node_id = iq.pubsub.create.getAttribute("node")
        if not node_id or node_id != result:
            reply = domish.Element((NS_PUBSUB, 'pubsub'))
            entity = reply.addElement('create')
            entity['node'] = result
            return [reply]

    def onDefault(self, iq):
        self.handler_wrapper(self._onDefault, iq)

    def _onDefault(self, iq):
        d = self.backend.get_default_configuration()
        d.addCallback(self._return_default_response)
        return d
        
    def _return_default_response(self, options):
        reply = domish.Element((NS_PUBSUB_OWNER, "pubsub"))
        default = reply.addElement("default")
        default.addChild(self._form_from_configuration(options))

        return [reply]

    def onConfigureGet(self, iq):
        self.handler_wrapper(self._onConfigureGet, iq)

    def _onConfigureGet(self, iq):
        node_id = iq.pubsub.configure.getAttribute("node")

        d = self.backend.get_node_configuration(node_id)
        d.addCallback(self._return_configuration_response, node_id)
        return d

    def _return_configuration_response(self, options, node_id):
        reply = domish.Element((NS_PUBSUB_OWNER, "pubsub"))
        configure = reply.addElement("configure")
        if node_id:
            configure["node"] = node_id
        configure.addChild(self._form_from_configuration(options))

        return [reply]

    def _form_from_configuration(self, options):
        form = data_form.Form(type="form",
                              form_type=NS_PUBSUB + "#node_config")

        for option in options:
            form.add_field(**option)

        return form

    def onConfigureSet(self, iq):
        print "onConfigureSet"
        self.handler_wrapper(self._onConfigureSet, iq)

    def _onConfigureSet(self, iq):
        node_id = iq.pubsub.configure["node"]
        requestor = jid.internJID(iq["from"]).userhostJID()

        for element in iq.pubsub.configure.elements():
            if element.name != 'x' or element.uri != data_form.NS_X_DATA:
                continue

            type = element.getAttribute("type")
            if type == "cancel":
                return None
            elif type != "submit":
                continue

            options = self._get_form_options(element)

            if options["FORM_TYPE"] == NS_PUBSUB + "#node_config":
                del options["FORM_TYPE"]
                return self.backend.set_node_configuration(node_id,
                                                           options,
                                                           requestor)
        
        raise BadRequest

    def _get_form_options(self, form):
        options = {}

        for element in form.elements():
            if element.name == 'field' and element.uri == data_form.NS_X_DATA:
                try:
                    options[element["var"]] = str(element.value)
                except (KeyError, AttributeError):
                    raise BadRequest

        return options

components.registerAdapter(ComponentServiceFromNodeCreationService,
                           backend.INodeCreationService,
                           IService)

class ComponentServiceFromAffiliationsService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_AFFILIATIONS, self.onAffiliations)

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + "#retrieve-affiliations"))

        return defer.succeed(info)

    def onAffiliations(self, iq):
        self.handler_wrapper(self._onAffiliations, iq)

    def _onAffiliations(self, iq):
        entity = jid.internJID(iq["from"]).userhostJID()
        d = self.backend.get_affiliations(entity)
        d.addCallback(self._return_affiliations_response, iq)
        return d

    def _return_affiliations_response(self, result, iq):
        reply = domish.Element((NS_PUBSUB, 'pubsub'))
        affiliations = reply.addElement('affiliations')
        for node, affiliation in result:
            item = affiliations.addElement('affiliation')
            item['node'] = node
            item['affiliation'] = affiliation
        return [reply]

components.registerAdapter(ComponentServiceFromAffiliationsService,
                           backend.IAffiliationsService,
                           IService)

class ComponentServiceFromItemRetrievalService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_ITEMS, self.onItems)

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + "#retrieve-items"))

        return defer.succeed(info)

    def onItems(self, iq):
        self.handler_wrapper(self._onItems, iq)

    def _onItems(self, iq):
        try:
            node_id = iq.pubsub.items["node"]
        except KeyError:
            raise BadRequest

        max_items = iq.pubsub.items.getAttribute('max_items')

        if max_items:
            try:
                max_items = int(max_items)
            except ValueError:
                raise BadRequest

        item_ids = []
        for child in iq.pubsub.items.elements():
            if child.name == 'item' and child.uri == NS_PUBSUB:
                try:
                    item_ids.append(child["id"])
                except KeyError:
                    raise BadRequest
       
        d = self.backend.get_items(node_id,
                                   jid.internJID(iq["from"]),
                                   max_items,
                                   item_ids)
        d.addCallback(self._return_items_response, node_id)
        return d

    def _return_items_response(self, result, node_id):
        reply = domish.Element((NS_PUBSUB, 'pubsub'))
        items = reply.addElement('items')
        items["node"] = node_id
        for r in result:
            items.addRawXml(r)

        return [reply]

components.registerAdapter(ComponentServiceFromItemRetrievalService,
                           backend.IItemRetrievalService,
                           IService)

class ComponentServiceFromRetractionService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_RETRACT, self.onRetract)
        xmlstream.addObserver(PUBSUB_PURGE, self.onPurge)

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + "#delete-any"))
            info.append(disco.Feature(NS_PUBSUB + "#retract-items"))
            info.append(disco.Feature(NS_PUBSUB + "#purge-nodes"))

        return defer.succeed(info)

    def onRetract(self, iq):
        self.handler_wrapper(self._onRetract, iq)

    def _onRetract(self, iq):
        try:
            node = iq.pubsub.retract["node"]
        except KeyError:
            raise BadRequest

        item_ids = []
        for child in iq.pubsub.retract.children:
            if child.__class__ == domish.Element and child.name == 'item':
                try:
                    item_ids.append(child["id"])
                except KeyError:
                    raise BadRequest

        requestor = jid.internJID(iq["from"]).userhostJID()
        return self.backend.retract_item(node, item_ids, requestor)

    def onPurge(self, iq):
        self.handler_wrapper(self._onPurge, iq)

    def _onPurge(self, iq):
        try:
            node = iq.pubsub.purge["node"]
        except KeyError:
            raise BadRequest

        return self.backend.purge_node(node,
                           jid.internJID(iq["from"]).userhostJID())

components.registerAdapter(ComponentServiceFromRetractionService,
                           backend.IRetractionService,
                           IService)

class ComponentServiceFromNodeDeletionService(Service):

    def __init__(self, backend):
        Service.__init__(self, backend)
        self.subscribers = []

    def componentConnected(self, xmlstream):
        self.backend.register_pre_delete(self._pre_delete)
        xmlstream.addObserver(PUBSUB_DELETE, self.onDelete)

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + "#delete-nodes"))

        return defer.succeed(info)

    def _pre_delete(self, node_id):
        d = self.backend.get_subscribers(node_id)
        d.addCallback(self._return_deferreds, node_id)
        return d

    def _return_deferreds(self, subscribers, node_id):
        d = defer.Deferred()
        d.addCallback(self._notify, subscribers, node_id)
        return [d]

    def _notify(self, result, subscribers, node_id):
        message = domish.Element((NS_COMPONENT, "message"))
        message["from"] = self.parent.jabberId
        event = message.addElement((NS_PUBSUB_EVENT, "event"))
        event.addElement("delete")["node"] = node_id

        for subscriber in subscribers:
            message["to"] = subscriber
            self.send(message)

    def onDelete(self, iq):
        self.handler_wrapper(self._onDelete, iq)

    def _onDelete(self, iq):
        try:
            node = iq.pubsub.delete["node"]
        except KeyError:
            raise BadRequest

        return self.backend.delete_node(node,
                            jid.internJID(iq["from"]).userhostJID())

components.registerAdapter(ComponentServiceFromNodeDeletionService,
                           backend.INodeDeletionService,
                           IService)

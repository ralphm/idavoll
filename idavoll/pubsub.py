from twisted.protocols.jabber import component,jid
from twisted.xish import utility, domish
from twisted.python import components
from twisted.internet import defer

import backend
import xmpp_error
import disco

NS_COMPONENT = 'jabber:component:accept'
NS_PUBSUB = 'http://jabber.org/protocol/pubsub'
NS_PUBSUB_EVENT = NS_PUBSUB + '#event'
NS_PUBSUB_ERRORS = NS_PUBSUB + '#errors'
NS_PUBSUB_OWNER = NS_PUBSUB + "#owner"
NS_X_DATA = 'jabber:x:data'

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
PUBSUB_CONFIGURE_GET = PUBSUB_OWNER_GET + '/configure'
PUBSUB_CONFIGURE_SET = PUBSUB_OWNER_SET + '/configure'
PUBSUB_AFFILIATIONS = PUBSUB_GET + '/affiliations'
PUBSUB_ITEMS = PUBSUB_GET + '/items'
PUBSUB_RETRACT = PUBSUB_SET + '/retract'
PUBSUB_PURGE = PUBSUB_SET + '/purge'
PUBSUB_DELETE = PUBSUB_SET + '/delete'

class Error(Exception):
    pubsub_error = None
    stanza_error = None
    msg = ''

class NotImplemented(Error):
    stanza_error = 'feature-not-implemented'

class BadRequest(Error):
    stanza_error = 'bad-request'

class OptionsUnavailable(Error):
    stanza_error = 'feature-not-implemented'
    pubsub_error = 'subscription-options-unavailable'

class NodeNotConfigurable(Error):
    stanza_error = 'feature-not-implemented'
    pubsub_error = 'node-not-configurable'

error_map = {
    backend.NotAuthorized:      ('not-authorized', None),
    backend.NodeNotFound:       ('item-not-found', None),
    backend.NoPayloadAllowed:   ('bad-request', None),
    backend.PayloadExpected:    ('bad-request', None),
    backend.NoInstantNodes:     ('not-acceptable', None),
    backend.NodeExists:         ('conflict', None),
    backend.NotImplemented:     ('feature-not-implemented', None),
    backend.NotSubscribed:      ('not-authorized', 'requestor-not-subscribed'),
}

class Service(component.Service):

    __implements__ = component.IService

    def __init__(self, backend):
        self.backend = backend

    def error(self, failure, iq):
        try: 
            e = failure.trap(Error, *error_map.keys())
        except:
            failure.printBriefTraceback()
            xmpp_error.error_from_iq(iq, 'internal-server-error')
            return iq
        else:
            if e == Error:
                stanza_error = failure.value.stanza_error
                pubsub_error = failure.value.pubsub_error
                msg = ''
            else:
                stanza_error, pubsub_error = error_map[e]
                msg = failure.value.msg

            xmpp_error.error_from_iq(iq, stanza_error, msg)
            if pubsub_error:
                iq.error.addElement((NS_PUBSUB_ERRORS, pubsub_error))
            return iq
    
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

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Identity('pubsub', 'generic',
                                       'Generic Pubsub Service'))

            if self.backend.supports_publisher_affiliation():
                info.append(disco.Feature(NS_PUBSUB + "#publisher-affiliation"))

            if self.backend.supports_outcast_affiliation():
                info.append(disco.Feature(NS_PUBSUB + "#outcast-affiliation"))

            if self.backend.supports_persistent_items():
                info.append(disco.Feature(NS_PUBSUB + "#persistent-items"))

            return defer.succeed(info)
        else:
            d = self.backend.get_node_type(node)
            d.addCallback(lambda x: [disco.Identity('pubsub', x)])
            d.addErrback(lambda _: [])
            return d

    def get_disco_items(self, node):
        if node:
            return defer.succeed([])
        
        d = self.backend.get_nodes()
        d.addCallback(lambda nodes: [disco.Item(self.parent.jabberId, node)
                                    for node in nodes])
        return d

components.registerAdapter(ComponentServiceFromService, backend.IBackendService, component.IService)

class ComponentServiceFromNotificationService(Service):

    def componentConnected(self, xmlstream):
        self.backend.register_notifier(self.notify)
        
    def notify(self, object):
        node_id = object["node_id"]
        items = object["items"]
        d = self.backend.get_notification_list(node_id, items)
        d.addCallback(self._notify, node_id)

    def _notify(self, list, node_id):
        print list
        for recipient, items in list.items():
            self._notify_recipient(recipient, node_id, items)

    def _notify_recipient(self, recipient, node_id, itemlist):
        message = domish.Element((NS_COMPONENT, "message"))
        message["from"] = self.parent.jabberId
        message["to"] = recipient
        event = message.addElement((NS_PUBSUB_EVENT, "event"))
        items = event.addElement("items")
        items["node"] = node_id
        items.children.extend(itemlist)
        self.send(message)

components.registerAdapter(ComponentServiceFromNotificationService, backend.INotificationService, component.IService)

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
        node = iq.pubsub.publish["node"]

        items = []
        for child in iq.pubsub.publish.children:
            if child.__class__ == domish.Element and child.name == 'item':
                items.append(child)

        print items

        return self.backend.publish(node, items,
                                    jid.JID(iq["from"]).userhostJID())

components.registerAdapter(ComponentServiceFromPublishService, backend.IPublishService, component.IService)

class ComponentServiceFromSubscriptionService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_SUBSCRIBE, self.onSubscribe)
        xmlstream.addObserver(PUBSUB_UNSUBSCRIBE, self.onUnsubscribe)
        xmlstream.addObserver(PUBSUB_OPTIONS_GET, self.onOptionsGet)
        xmlstream.addObserver(PUBSUB_OPTIONS_SET, self.onOptionsSet)
    
    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + '#subscribe'))

        return defer.succeed(info)

    def onSubscribe(self, iq):
        self.handler_wrapper(self._onSubscribe, iq)

    def _onSubscribe(self, iq):
        try:
            node_id = iq.pubsub.subscribe["node"]
            subscriber = jid.JID(iq.pubsub.subscribe["jid"])
        except KeyError:
            raise BadRequest

        requestor = jid.JID(iq["from"]).userhostJID()
        d = self.backend.subscribe(node_id, subscriber, requestor)
        d.addCallback(self.return_subscription)
        return d

    def return_subscription(self, result):
        reply = domish.Element((NS_PUBSUB, "pubsub"))
        entity = reply.addElement("entity")
        entity["node"] = result["node"]
        entity["jid"] = result["jid"].full()
        entity["affiliation"] = result["affiliation"] or 'none'
        entity["subscription"] = result["subscription"]
        return [reply]

    def onUnsubscribe(self, iq):
        self.handler_wrapper(self._onUnsubscribe, iq)

    def _onUnsubscribe(self, iq):
        try:
            node_id = iq.pubsub.unsubscribe["node"]
            subscriber = jid.JID(iq.pubsub.unsubscribe["jid"])
        except KeyError:
            raise BadRequest

        requestor = jid.JID(iq["from"]).userhostJID()
        return self.backend.unsubscribe(node_id, subscriber, requestor)

    def onOptionsGet(self, iq):
        self.handler_wrapper(self._onOptionsGet, iq)

    def _onOptionsGet(self, iq):
        raise OptionsUnavailable

    def onOptionsSet(self, iq):
        self.handler_wrapper(self._onOptionsSet, iq)

    def _onOptionsSet(self, iq):
        raise OptionsUnavailable

components.registerAdapter(ComponentServiceFromSubscriptionService, backend.ISubscriptionService, component.IService)

class ComponentServiceFromNodeCreationService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_CREATE, self.onCreate)
        xmlstream.addObserver(PUBSUB_CONFIGURE_GET, self.onConfigureGet)
        xmlstream.addObserver(PUBSUB_CONFIGURE_SET, self.onConfigureSet)

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + "#create-nodes"))
            info.append(disco.Feature(NS_PUBSUB + "#config-node"))

            if self.backend.supports_instant_nodes():
                info.append(disco.Feature(NS_PUBSUB + "#instant-nodes"))

        return defer.succeed(info)

    def onCreate(self, iq):
        self.handler_wrapper(self._onCreate, iq)

    def _onCreate(self, iq):
        node = iq.pubsub.create.getAttribute("node")

        owner = jid.JID(iq["from"]).userhostJID()

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

    def onConfigureGet(self, iq):
        self.handler_wrapper(self._onConfigureGet, iq)

    def _onConfigureGet(self, iq):
        try:
            node_id = iq.pubsub.configure["node"]
        except KeyError:
            raise NodeNotConfigurable

        d = self.backend.get_node_configuration(node_id)
        d.addCallback(self._return_configuration_response, node_id)
        return d

    def _return_configuration_response(self, options, node_id):
        reply = domish.Element((NS_PUBSUB_OWNER, "pubsub"))
        configure = reply.addElement("configure")
        if node_id:
            configure["node"] = node_id
        form = configure.addElement((NS_X_DATA, "x"))
        form["type"] = "form"
        field = form.addElement("field")
        field["var"] = "FORM_TYPE"
        field["type"] = "hidden"
        field.addElement("value", content=NS_PUBSUB + "#node_config")

        for option in options:
            field = form.addElement("field")
            field["var"] = option["var"]
            field["type"] = option["type"]
            field["label"] = option["label"]
            field.addElement("value", content=option["value"])

        return [reply]

    def onConfigureSet(self, iq):
        self.handler_wrapper(self._onConfigureSet, iq)

    def _onConfigureSet(self, iq):
        try:
            node_id = iq.pubsub.configure["node"]
        except KeyError:
            raise BadRequest

        requestor = jid.JID(iq["from"]).userhostJID()

        for element in iq.pubsub.configure.elements():
            if element.name != 'x' or element.uri != NS_X_DATA:
                continue

            type = element.getAttribute("type")
            if type == "cancel":
                return None
            elif type != "submit":
                continue

            try:
                options = self._get_form_options(element)
            except:
                raise BadRequest

            if options["FORM_TYPE"] == NS_PUBSUB + "#node_config":
                del options["FORM_TYPE"]
                return self.backend.set_node_configuration(node_id,
                                                           options,
                                                           requestor)
        
        raise BadRequest

    def _get_form_options(self, form):
        options = {}

        for element in form.elements():
            if element.name == 'field' and element.uri == NS_X_DATA:
                options[element["var"]] = str(element.value)

        print options
        return options

components.registerAdapter(ComponentServiceFromNodeCreationService, backend.INodeCreationService, component.IService)

class ComponentServiceFromAffiliationsService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_AFFILIATIONS, self.onAffiliations)

    def onAffiliations(self, iq):
        self.handler_wrapper(self._onAffiliations, iq)

    def _onAffiliations(self, iq):
        d = self.backend.get_affiliations(jid.JID(iq["from"]).userhostJID())
        d.addCallback(self._return_affiliations_response, iq)
        return d

    def _return_affiliations_response(self, result, iq):
        reply = domish.Element((NS_PUBSUB, 'pubsub'))
        affiliations = reply.addElement('affiliations')
        for r in result:
            entity = affiliations.addElement('entity')
            entity['node'] = r['node']
            entity['jid'] = r['jid'].full()
            entity['affiliation'] = r['affiliation'] or 'none'
            entity['subscription'] = r['subscription'] or 'none'
        return [reply]

components.registerAdapter(ComponentServiceFromAffiliationsService, backend.IAffiliationsService, component.IService)

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
        for child in iq.pubsub.items.children:
            if child.name == 'item' and child.uri == NS_PUBSUB:
                try:
                    item_ids.append(child["id"])
                except KeyError:
                    raise BadRequest
       
        d = self.backend.get_items(node_id, jid.JID(iq["from"]), max_items,
                                   item_ids)
        d.addCallback(self._return_items_response, node_id)
        return d

    def _return_items_response(self, result, node_id):
        reply = domish.Element((NS_PUBSUB, 'pubsub'))
        items = reply.addElement('items')
        items["node"] = node_id
        try:
            for r in result:
                items.addRawXml(r)
        except Exception, e:
            print e

        return [reply]

components.registerAdapter(ComponentServiceFromItemRetrievalService, backend.IItemRetrievalService, component.IService)

class ComponentServiceFromRetractionService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_RETRACT, self.onRetract)
        xmlstream.addObserver(PUBSUB_PURGE, self.onPurge)

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(NS_PUBSUB + "#delete-any"))

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

        print item_ids

        return self.backend.retract_item(node, item_ids,
                                    jid.JID(iq["from"]).userhostJID())

    def onPurge(self, iq):
        self.handler_wrapper(self._onPurge, iq)

    def _onPurge(self, iq):
        try:
            node = iq.pubsub.purge["node"]
        except KeyError:
            raise BadRequest

        return self.backend.purge_node(node, jid.JID(iq["from"]).userhostJID())

components.registerAdapter(ComponentServiceFromRetractionService, backend.IRetractionService, component.IService)

class ComponentServiceFromNodeDeletionService(Service):

    def __init__(self, backend):
        Service.__init__(self, backend)
        self.subscribers = []

    def componentConnected(self, xmlstream):
        self.backend.register_pre_delete(self._pre_delete)
        xmlstream.addObserver(PUBSUB_DELETE, self.onDelete)

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
            print message.toXml()
            self.send(message)

    def onDelete(self, iq):
        self.handler_wrapper(self._onDelete, iq)

    def _onDelete(self, iq):
        try:
            node = iq.pubsub.delete["node"]
        except KeyError:
            raise BadRequest

        return self.backend.delete_node(node, jid.JID(iq["from"]).userhostJID())

components.registerAdapter(ComponentServiceFromNodeDeletionService, backend.INodeDeletionService, component.IService)

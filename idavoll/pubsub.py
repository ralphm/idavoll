from twisted.protocols.jabber import component,jid
from twisted.xish import utility, domish
from twisted.python import components
from twisted.internet import defer

import backend
import xmpp_error

NS_COMPONENT = 'jabber:component:accept'
NS_PUBSUB = 'http://jabber.org/protocol/pubsub'
NS_PUBSUB_EVENT = NS_PUBSUB + '#event'
NS_PUBSUB_ERRORS = NS_PUBSUB + '#errors'

IQ_GET = '/iq[@type="get"]'
IQ_SET = '/iq[@type="set"]'
PUBSUB_ELEMENT = '/pubsub[@xmlns="' + NS_PUBSUB + '"]'
PUBSUB_GET = IQ_GET + PUBSUB_ELEMENT
PUBSUB_SET = IQ_SET + PUBSUB_ELEMENT
PUBSUB_CREATE = PUBSUB_SET + '/create'
PUBSUB_PUBLISH = PUBSUB_SET + '/publish'
PUBSUB_SUBSCRIBE = PUBSUB_SET + '/subscribe'
PUBSUB_UNSUBSCRIBE = PUBSUB_SET + '/unsubscribe'
PUBSUB_OPTIONS_GET = PUBSUB_GET + '/options'
PUBSUB_OPTIONS_SET = PUBSUB_SET + '/options'
PUBSUB_CONFIGURE_GET = PUBSUB_GET + '/configure'
PUBSUB_CONFIGURE_SET = PUBSUB_SET + '/configure'
PUBSUB_AFFILIATIONS = PUBSUB_GET + '/affiliations'

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

class SubscriptionOptionsUnavailable(Error):
    stanza_error = 'not-acceptable'
    pubsub_error = 'subscription-options-unavailable'

class NodeNotConfigurable(Error):
    stanza_error = 'feature-not-implemented'
    pubsub_error = 'node-not-configurable'

class CreateNodeNotConfigurable(Error):
    stanza_error = 'not-acceptable'
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
        except:
            xmpp_error.error_from_iq(iq, 'internal-server-error')
            self.send(iq)
            raise
    
    def success(self, result, iq):
        iq.swapAttributeValues("to", "from")
        iq["type"] = 'result'
        iq.children = result or []
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

    def getIdentities(self, node):
        results = []
        if not node:
            results.append({
                'category': 'pubsub',
                'type': 'generic',
                'name': 'Generic Pubsub Service'
            })
        return results

    def getFeatures(self, node):
        features = []

        if not node:
            if self.backend.supports_publisher_affiliation():
                features.append(NS_PUBSUB + "#publisher-affiliation")

            if self.backend.supports_outcast_affiliation():
                features.append(NS_PUBSUB + "#outcast-affiliation")

            if self.backend.supports_persistent_items():
                features.append(NS_PUBSUB + "#persistent-items")

        return features

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
    
    def getFeatures(self, node):
        features = []

        if not node:
            features.append(NS_PUBSUB + "#subscribe")

        return features

    def onSubscribe(self, iq):
        self.handler_wrapper(self._onSubscribe, iq)

    def _onSubscribe(self, iq):
        if iq.pubsub.options:
            raise SubscribeOptionsUnavailable

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

    def getFeatures(self, node):
        features = []

        if not node:
            features.append(NS_PUBSUB + "#create-nodes")

            if self.backend.supports_instant_nodes():
                features.append(NS_PUBSUB + "#instant-nodes")

        return features

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_CREATE, self.onCreate)
        xmlstream.addObserver(PUBSUB_CONFIGURE_GET, self.onConfigureGet)
        xmlstream.addObserver(PUBSUB_CONFIGURE_SET, self.onConfigureSet)

    def onCreate(self, iq):
        self.handler_wrapper(self._onCreate, iq)

    def _onCreate(self, iq):
        if iq.pubsub.options:
            raise CreateNodeNotConfigurable

        node = iq.pubsub.create.getAttribute("node")

        owner = jid.JID(iq["from"]).userhostJID()

        d = self.backend.create_node(node, owner)
        d.addCallback(self.return_create_response, iq)
        return d

    def return_create_response(self, result, iq):
        if iq.pubsub.create["node"] is None:
            reply = domish.Element((NS_PUBSUB, 'pubsub'))
            entity = reply.addElement('create')
            entity['node'] = result['node_id']
            return [reply]

    def onConfigureGet(self, iq):
        self.handler_wrapper(self._onConfigureGet, iq)

    def _onConfigureGet(self, iq):
        raise NodeNotConfigurable

    def onConfigureSet(self, iq):
        self.handler_wrapper(self._onConfigureSet, iq)

    def _onConfigureSet(self, iq):
        raise NodeNotConfigurable

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

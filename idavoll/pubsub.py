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
PUBSUB_OPTIONS_GET = PUBSUB_GET + '/options'
PUBSUB_OPTIONS_SET = PUBSUB_SET + '/options'
PUBSUB_CONFIGURE_GET = PUBSUB_GET + '/configure'
PUBSUB_CONFIGURE_SET = PUBSUB_SET + '/configure'

class PubSubError(Exception):
    pubsub_error = None
    msg = ''

class NotImplemented(PubSubError):
    pass

class OptionsUnavailable(PubSubError):
    pubsub_error = 'subscription-options-unavailable'

class SubscriptionOptionsUnavailable(PubSubError):
    pubsub_error = 'subscription-options-unavailable'

class NodeNotConfigurable(PubSubError):
    pubsub_error = 'node-not-configurable'

class CreateNodeNotConfigurable(PubSubError):
    pubsub_error = 'node-not-configurable'

error_map = {
    backend.NotAuthorized:          'not-authorized',
    backend.NodeNotFound:           'item-not-found',
    backend.NoPayloadAllowed:       'bad-request',
    backend.PayloadExpected:        'bad-request',
    backend.NoInstantNodes:         'not-acceptable',
    backend.NodeExists:             'conflict',
    backend.NotImplemented:         'feature-not-implemented',
    NotImplemented:                 'feature-not-implemented',
    OptionsUnavailable:             'feature-not-implemented',
    SubscriptionOptionsUnavailable: 'not-acceptable',
    NodeNotConfigurable:            'feature-not-implemented',
    CreateNodeNotConfigurable:      'not-acceptable',
}

class Service(component.Service):

    __implements__ = component.IService

    def __init__(self, backend):
        self.backend = backend

    def componentConnected(self, xmlstream):
        pass

    def error(self, failure, iq):
        try: 
            r = failure.trap(*error_map.keys())
            xmpp_error.error_from_iq(iq, error_map[r], failure.value.msg)
            if isinstance(failure.value, PubSubError) and \
               failure.value.pubsub_error is not None:
                iq.error.addElement((NS_PUBSUB_ERRORS,
                                     failure.value.pubsub_error),
                                    NS_PUBSUB_ERRORS)
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

        affiliations = self.backend.get_supported_affiliations()
        if 'outcast' in affiliations:
            features.append("http://jabber.org/protocol/pubsub#outcast-affil")

        if 'publisher' in affiliations:
            features.append("http://jabber.org/protocol/pubsub#publisher-affil")

        # "http://jabber.org/protocol/pubsub#persistent-items"

        return features

components.registerAdapter(ComponentServiceFromService, backend.IBackendService, component.IService)

class ComponentServiceFromNotificationService(Service):

    def __init__(self, backend):
        Service.__init__(self, backend)
        self.backend.register_notifier(self.notify)
        
    def notify(self, object):
        node_id = object["node_id"]
        items = object["items"]
        d = self.backend.get_notification_list(node_id, items)
        d.addCallback(self._notify, node_id)

    def _notify(self, list, node_id):
        for recipient, items in list.items():
            self._notify_recipient(recipient, node_id, items)

    def _notify_recipient(self, recipient, node_id, itemlist):
        message = domish.Element((NS_COMPONENT, "message"))
        message["from"] = self.parent.jabberId
        message["to"] = recipient
        event = message.addElement((NS_PUBSUB_EVENT, "event"), NS_PUBSUB_EVENT)
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

    def onSubscribe(self, iq):
        self.handler_wrapper(self._onSubscribe, iq)

    def _onSubscribe(self, iq):
        if iq.pubsub.options:
            raise SubscribeOptionsUnavailable

        node_id = iq.pubsub.subscribe["node"]
        subscriber = jid.JID(iq.pubsub.subscribe["jid"])
        requestor = jid.JID(iq["from"]).userhostJID()
        d = self.backend.do_subscribe(node_id, subscriber, requestor)
        d.addCallback(self.return_subscription)
        d.addCallback(self.succeed, iq)
        d.addErrback(self.error, iq)
        d.addCallback(self.send)

    def _onConfigureGet(self, iq):
        raise NodeNotConfigurable

    def _onConfigureSet(self, iq):
        raise NodeNotConfigurable

    def return_subscription(self, result):
        reply = domish.Element("pubsub", NS_PUBSUB)
        entity = reply.addElement("entity")
        entity["node"] = result["node"]
        entity["jid"] = result["jid"].full()
        entity["affiliation"] = result["affiliation"]
        entity["subscription"] = result["subscription"]
        return reply

components.registerAdapter(ComponentServiceFromSubscriptionService, backend.ISubscriptionService, component.IService)

class ComponentServiceFromNodeCreationService(Service):

    def componentConnected(self, xmlstream):
        xmlstream.addObserver(PUBSUB_CREATE, self.onCreate)

    def onCreate(self, iq):
        self.handler_wrapper(self._onCreate, iq)

    def _onCreate(self, iq):
        if iq.pubsub.options:
            raise CreateNodeNotConfigurable

        node = iq.pubsub.create["node"]
        owner = jid.JID(iq["from"]).userhostJID()

        d = self.backend.create_node(node, owner)
        d.addCallback(self.return_create_response, iq)
        return d

    def _onOptionsGet(self, iq):
        raise OptionsUnavailable

    def _onOptionsSet(self, iq):
        raise OptionsUnavailable

    def return_create_response(self, result, iq):
        if iq.pubsub.create["node"] is None:
            reply = domish.Element('pubsub', NS_PUBSUB)
            entity = reply.addElement('create')
            entity['node'] = result['node_id']
            return reply

components.registerAdapter(ComponentServiceFromNodeCreationService, backend.INodeCreationService, component.IService)

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
	backend.NotAuthorized:			'not-authorized',
	backend.NodeNotFound:			'item-not-found',
	backend.NoPayloadAllowed:		'bad-request',
	backend.PayloadExpected:		'bad-request',
	backend.NoInstantNodes:			'not-acceptable',
	backend.NodeExists:				'conflict',
	NotImplemented:					'feature-not-implemented',
	OptionsUnavailable:				'feature-not-implemented',
	SubscriptionOptionsUnavailable:	'not-acceptable',
	NodeNotConfigurable:			'feature-not-implemented',
	CreateNodeNotConfigurable:		'not-acceptable',
}

class ComponentServiceFromBackend(component.Service):

	def __init__(self, backend):
		self.backend = backend
		self.backend.pubsub_service = self
		
	def componentConnected(self, xmlstream):
		xmlstream.addObserver(PUBSUB_SET, self.onPubSub)
		xmlstream.addObserver(PUBSUB_GET, self.onPubSub)

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
		return [
			"http://jabber.org/protocol/pubsub#outcast-affil",
			"http://jabber.org/protocol/pubsub#publisher-affil",
			"http://jabber.org/protocol/pubsub#persistent-items",
			]

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

	def onPubSub(self, iq):
		for elem in iq.pubsub.elements():
			if not elem.hasAttribute('xmlns'):
				action = elem.name
				break

		if not action:
			return

		try:
			try:
				handler = getattr(self, 'on%s%s' % (action.capitalize(),
													iq["type"].capitalize()))
			except KeyError:
				raise NotImplemented
			else:
				d = handler(iq)
		except:
			d = defer.fail()
				
		d.addCallback(self.success, iq)
		d.addErrback(self.error, iq)
		d.addCallback(self.send)
		iq.handled = True

	# action handlers

	def onPublishSet(self, iq):
		node = iq.pubsub.publish["node"]

		items = []
		for child in iq.pubsub.publish.children:
			if child.__class__ == domish.Element and child.name == 'item':
				items.append(child)

		print items

		return self.backend.do_publish(node,
				                       jid.JID(iq["from"]).userhost(),
									   items)

	def onOptionsGet(self, iq):
		raise OptionsUnavailable

	def onOptionsSet(self, iq):
		raise OptionsUnavailable

	def onConfigureGet(self, iq):
		raise NodeNotConfigurable

	def onConfigureSet(self, iq):
		raise NodeNotConfigurable

	def onSubscribeSet(self, iq):
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

	def return_subscription(self, result):
		reply = domish.Element("pubsub", NS_PUBSUB)
		entity = reply.addElement("entity")
		entity["node"] = result["node"]
		entity["jid"] = result["jid"].full()
		entity["affiliation"] = result["affiliation"]
		entity["subscription"] = result["subscription"]
		return reply

	def onCreateSet(self, iq):
		if iq.pubsub.options:
			raise CreateNodeNotConfigurable

		node = iq.pubsub.create["node"]
		owner = jid.JID(iq["from"]).userhostJID()

		d = self.backend.create_node(node, owner)
		d.addCallback(self.return_create_response, iq)
		return d

	def return_create_response(self, result, iq):
		if iq.pubsub.create["node"] is None:
			reply = domish.Element('pubsub', NS_PUBSUB)
			entity = reply.addElement('create')
			entity['node'] = result['node_id']
			return reply

	# other methods

	def do_notification(self, list, node):
		for recipient, items in list.items():
			self.notify(node, items, recipient)

	def notify(self, node, itemlist, recipient):
		message = domish.Element((NS_COMPONENT, "message"))
		message["from"] = self.parent.jabberId
		message["to"] = recipient
		event = message.addElement((NS_PUBSUB_EVENT, "event"), NS_PUBSUB_EVENT)
		items = event.addElement("items")
		items["node"] = node
		items.children.extend(itemlist)
		self.send(message)
		
components.registerAdapter(ComponentServiceFromBackend, backend.IService, component.IService)


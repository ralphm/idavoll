from twisted.protocols.jabber import component,jid
from twisted.xish import utility, domish
from twisted.python import components
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
PUBSUB_CONFIGURE_GET = PUBSUB_GET + '/configure'

error_map = {
	backend.NotAuthorized:			'not-authorized',
	backend.NodeNotFound:			'item-not-found',
	backend.NoPayloadAllowed:		'bad-request',
	backend.PayloadExpected:		'bad-request',
}

class ComponentServiceFromBackend(component.Service, utility.EventDispatcher):

	def __init__(self, backend):
		utility.EventDispatcher.__init__(self)
		self.backend = backend
		self.backend.pubsub_service = self
		self.addObserver(PUBSUB_PUBLISH, self.onPublish)
		self.addObserver(PUBSUB_SUBSCRIBE, self.onSubscribe)
		self.addObserver(PUBSUB_OPTIONS_GET, self.onOptionsGet)
		self.addObserver(PUBSUB_CONFIGURE_GET, self.onConfigureGet)
		self.addObserver(PUBSUB_GET, self.notImplemented, -1)
		self.addObserver(PUBSUB_SET, self.notImplemented, -1)

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

	def notImplemented(self, iq):
		self.send(xmpp_error.error_from_iq(iq, 'feature-not-implemented'))

	def onPubSub(self, iq):
		self.dispatch(iq)
		iq.handled = True

	def onPublish(self, iq):
		node = iq.pubsub.publish["node"]

		items = []
		for child in iq.pubsub.publish.children:
			if child.__class__ == domish.Element and child.name == 'item':
				items.append(child)

		print items

		d = self.backend.do_publish(node, jid.JID(iq["from"]).userhost(), items)
		d.addCallback(self.success, iq)
		d.addErrback(self.error, iq)
		d.addCallback(self.send)

	def onOptionsGet(self, iq):
		xmpp_error.error_from_iq(iq, 'feature-not-implemented')
		iq.error.addElement((NS_PUBSUB_ERRORS, 'subscription-options-unavailable'), NS_PUBSUB_ERRORS)
		self.send(iq)

	def onConfigureGet(self, iq):
		xmpp_error.error_from_iq(iq, 'feature-not-implemented')
		iq.error.addElement((NS_PUBSUB_ERRORS, 'node-not-configurable'), NS_PUBSUB_ERRORS)
		self.send(iq)

	def onSubscribe(self, iq):
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

	def do_notification(self, list, node):

		for recipient, items in list.items():
			self.notify(node, items, recipient)

	def notify(self, node, itemlist, recipient):
		message = domish.Element((NS_COMPONENT, "message"))
		message["from"] = self.parent.jabberId
		message["to"] = recipient
		x = message.addElement((NS_PUBSUB_EVENT, "x"), NS_PUBSUB_EVENT)
		items = x.addElement("items")
		items["node"] = node
		items.children.extend(itemlist)
		self.send(message)
		
"""
	def onCreateSet(self, iq):
		node = iq.pubsub.create["node"]
		owner = jid.JID(iq["from"]).userhost()

		try:
			node = self.backend.create_node(node, owner)

			if iq.pubsub.create["node"] == None:
				# also show node name
		except:
			pass

		iq.handled = True
"""

components.registerAdapter(ComponentServiceFromBackend, backend.IBackendService, component.IService)


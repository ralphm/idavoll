from twisted.protocols.jabber import component,jid
from twisted.xish import utility, domish
from twisted.python import components
import backend
import xmpp_error

NS_COMPONENT = 'jabber:component:accept'
NS_PUBSUB = 'http://jabber.org/protocol/pubsub'
NS_PUBSUB_EVENT = NS_PUBSUB + '#event'

IQ_GET = '/iq[@type="get"]'
IQ_SET = '/iq[@type="set"]'
PUBSUB_ELEMENT = '/pubsub[@xmlns="' + NS_PUBSUB + '"]'
PUBSUB_GET = IQ_GET + PUBSUB_ELEMENT
PUBSUB_SET = IQ_SET + PUBSUB_ELEMENT
PUBSUB_CREATE = PUBSUB_SET + '/create'
PUBSUB_PUBLISH = PUBSUB_SET + '/publish'

class ComponentServiceFromBackend(component.Service, utility.EventDispatcher):

	def __init__(self, backend):
		utility.EventDispatcher.__init__(self)
		self.backend = backend
		self.backend.pubsub_service = self
		self.addObserver(PUBSUB_PUBLISH, self.onPublish)

	def componentConnected(self, xmlstream):
		xmlstream.addObserver(PUBSUB_SET, self.onPubSub)
		xmlstream.addObserver(PUBSUB_GET, self.onPubSub)

	def error(self, failure, iq):
		r = failure.trap(backend.NotAuthorized, backend.NodeNotFound)

		if r == backend.NotAuthorized:
			xmpp_error.error_from_iq(iq, 'not-authorized', failure.value.msg)

		if r == backend.NodeNotFound:
			xmpp_error.error_from_iq(iq, 'item-not-found', failure.value.msg)

		return iq
	
	def success(self, result, iq):
		iq.swapAttributeValues("to", "from")
		iq["type"] = 'result'
		iq.children = []
		return iq

	def onPubSub(self, iq):
		self.dispatch(iq)
		iq.handled = True

	def onPublish(self, iq):
		node = iq.pubsub.publish["node"]

		d = self.backend.do_publish(node, jid.JID(iq["from"]).userhost(), iq.pubsub.publish.item)
		d.addCallback(self.success, iq)
		d.addErrback(self.error, iq)
		d.addCallback(self.send)

	def do_notification(self, recipients, node, item):

		for recipient in recipients:
			self.notify(node, item, recipient)

	def notify(self, node, item, recipient):
		message = domish.Element((NS_COMPONENT, "message"))
		message["from"] = self.parent.jabberId
		message["to"] = recipient
		x = message.addElement((NS_PUBSUB_EVENT, "x"), NS_PUBSUB_EVENT)
		items = x.addElement("items")
		items["node"] = node
		items.children.append(item)
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


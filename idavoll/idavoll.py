from twisted.protocols.jabber import component
from twisted.application import service
from twisted.python import components
import memory_backend
import pubsub
import xmpp_error

import sys

NS_DISCO = 'http://jabber.org/protocol/disco'
NS_DISCO_INFO = NS_DISCO + '#info'
NS_DISCO_ITEMS = NS_DISCO + '#items'
NS_VERSION = 'jabber:iq:version'

IQ_GET = '/iq[@type="get"]'
IQ_SET = '/iq[@type="set"]'
VERSION = IQ_GET + '/query[@xmlns="' + NS_VERSION + '"]'
DISCO_INFO = IQ_GET + '/query[@xmlns="' + NS_DISCO_INFO + '"]'
DISCO_ITEMS = IQ_GET + '/query[@xmlns="' + NS_DISCO_ITEMS + '"]'

class IdavollService(component.Service):

	def componentConnected(self, xmlstream):
		self.xmlstream = xmlstream
		xmlstream.addObserver(VERSION, self.onVersion, 1)
		xmlstream.addObserver(DISCO_INFO, self.onDiscoInfo, 1)
		xmlstream.addObserver(DISCO_ITEMS, self.onDiscoItems, 1)
		xmlstream.addObserver(IQ_GET, self.iqFallback, -1)
		xmlstream.addObserver(IQ_SET, self.iqFallback, -1)

	def getFeatures(self, node):
		if not node:
			return [NS_DISCO_ITEMS, NS_VERSION]
	
	def onVersion(self, iq):
		iq.swapAttributeValues("to", "from")
		iq["type"] = "result"
		name = iq.addElement("name", None, 'Idavoll')
		version = iq.addElement("version", None, '0.1')
		self.send(iq)
		iq.handled = True

	def onDiscoInfo(self, iq):
		identities = []
		features = []
		node = iq.query.getAttribute("node")

		for c in self.parent:
			if components.implements(c, component.IService):
				if hasattr(c, "getIdentities"):
					identities.extend(c.getIdentities(node))
				if hasattr(c, "getFeatures"):
					features.extend(c.getFeatures(node))

		if not features and not identities and not node:
			xmpp_error.error_from_iq(iq, 'item-not-found')
		else:
			iq.swapAttributeValues("to", "from")
			iq["type"] = "result"
			for identity in identities:
				i = iq.query.addElement("identity")
				i.attributes = identity
			print features
			for feature in features:
				f = iq.query.addElement("feature")
				f["var"] = feature

		self.send(iq)
		iq.handled = True

	def onDiscoItems(self, iq):
		iq.swapAttributeValues("to", "from")
		iq["type"] = "result"
		iq.query.children = []
		self.send(iq)
	
	def iqFallback(self, iq):
		if iq.handled == True:
			return

		self.send(xmpp_error.error_from_iq(iq, 'service-unavailable'))

def makeService(config):
	serviceCollection = service.MultiService()

	b = memory_backend.MemoryBackendService()

	# set up Jabber Component
	c = component.buildServiceManager(config["jid"], config["secret"],
			("tcp:%s:%s" % (config["rhost"], config["rport"])))

	s = component.IService(b)
	s.jid = config["jid"]
	s.setServiceParent(c)

	s = IdavollService()
	s.setServiceParent(c)

	c.setServiceParent(serviceCollection)

	# other stuff

	return c

from twisted.protocols.jabber import component
from twisted.application import service
import backend
import pubsub
import xmpp_error

import sys

IQ_GET = '/iq[@type="get"]'
IQ_SET = '/iq[@type="set"]'
VERSION = IQ_GET + '/query[@xmlns="jabber:iq:version"]'

class IdavollService(component.Service):

	def componentConnected(self, xmlstream):
		self.xmlstream = xmlstream
		xmlstream.addObserver(VERSION, self.onVersion, 1)
		xmlstream.addObserver(IQ_GET, self.iqFallback, -1)
		xmlstream.addObserver(IQ_SET, self.iqFallback, -1)
	
	def onVersion(self, iq):
		print "version?"
		iq.swapAttributeValues("to", "from")
		iq["type"] = "result"
		name = iq.addElement("name", None, 'Idavoll')
		version = iq.addElement("version", None, '0.1')
		self.send(iq)
		iq.handled = True

	def iqFallback(self, iq):
		if iq.handled == True:
			return

		self.send(xmpp_error.error_from_iq(iq, 'feature-not-implemented'))

def makeService(config):
	serviceCollection = service.MultiService()

	pss = backend.MemoryBackendService()

	# set up Jabber Component
	c = component.buildServiceManager(config["jid"], config["secret"],
			("tcp:%s:%s" % (config["rhost"], config["rport"])))

	s = component.IService(pss)
	s.jid = config["jid"]
	s.setServiceParent(c)

	s = IdavollService()
	s.setServiceParent(c)

	c.setServiceParent(serviceCollection)

	# other stuff

	return c

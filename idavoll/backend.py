from twisted.application import service
from twisted.python import components, failure
from twisted.internet import defer, reactor

class IBackendService(components.Interface):
	""" Interface to a backend service of a pubsub service """

	def do_publish(self, node, publisher, item):
		""" Returns a deferred that returns """

class BackendException(Exception):
	def __init__(self, msg = ''):
		self.msg = msg

	def __str__(self):
		return self.msg
	
class NodeNotFound(BackendException):
	#def __init__(self, msg = 'Node not found'):
	#	BackendException.__init__(self, msg)
	pass

class NotAuthorized(BackendException):
	pass

class MemoryBackendService(service.Service):

	__implements__ = IBackendService,

	def __init__(self):
		self.nodes = {"ralphm/test": 'test'}
		self.subscribers = {"ralphm/test": ["ralphm@ik.nu", "ralphm@doe.ik.nu"] }
		self.affiliations = {"ralphm/test": { "ralphm@ik.nu": "owner", "ralphm@se-135.se.wtb.tue.nl": 'publisher', 'ralphm@doe.ik.nu': 'publisher' } }

	def do_publish(self, node, publisher, item):
		try:
			try:
				result = self.nodes[node]
			except KeyError:
				raise NodeNotFound

			try:
				affiliation = self.affiliations[node][publisher]
				if affiliation not in ['owner', 'publisher']:
					raise NotAuthorized
			except KeyError:
				raise NotAuthorized()

			print "publish by %s to %s" % (publisher, node)

			recipients = self.get_subscribers(node)
			recipients.addCallback(self.magic_filter, node, item)
			recipients.addCallback(self.pubsub_service.do_notification, node, item)

			return defer.succeed(result)
		except:
			f = failure.Failure()
			return defer.fail(f)

	def magic_filter(self, subscribers, node, item):
		return subscribers

	def get_subscribers(self, node):
		d = defer.Deferred()
		try:
			result = self.subscribers[node]
		except:
			f = failure.Failure()
			reactor.callLater(0, d.errback, f)
		else:
			reactor.callLater(0, d.callback, result)

		return d


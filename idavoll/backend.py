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
	def __init__(self, msg = 'Node not found'):
		BackendException.__init__(self, msg)

class NotAuthorized(BackendException):
	pass

class PayloadExpected(BackendException):
	def __init__(self, msg = 'Payload expected'):
		BackendException.__init__(self, msg)

class NoPayloadAllowed(BackendException):
	def __init__(self, msg = 'No payload allowed'):
		BackendException.__init__(self, msg)

class MemoryBackendService(service.Service):

	__implements__ = IBackendService,

	def __init__(self):
		self.nodes = {
			"ralphm/mood/ralphm@ik.nu": {
				"persist_items": True,
				"deliver_payloads": True,
			}
		}
		self.subscribers = {
			"ralphm/mood/ralphm@ik.nu": [
				"notify@ik.nu/mood_monitor"
			]
		}
		self.affiliations = {
			"ralphm/mood/ralphm@ik.nu": {
				"ralphm@ik.nu": "owner",
				"ralphm@doe.ik.nu": "publisher"
			}
		}

	def do_publish(self, node, publisher, items):
		try:
			try:
				config = self.nodes[node]
				persist_items = config["persist_items"]
				deliver_payloads = config["deliver_payloads"]
			except KeyError:
				raise NodeNotFound

			try:
				affiliation = self.affiliations[node][publisher]
				if affiliation not in ['owner', 'publisher']:
					raise NotAuthorized
			except KeyError:
				raise NotAuthorized()

			# the following is under the assumption that the publisher
			# has to provide an item when the node is persistent, but
			# an empty notification is to be sent.

			if items and not persist_items and not deliver_payloads:
				raise NoPayloadAllowed
			elif not items and (persist_items or deliver_payloads):
				raise PayloadExpected

			print "publish by %s to %s" % (publisher, node)

			if persist_items or deliver_payloads:
				for item in items:
					if item["id"] is None:
						item["id"] = 'random'

			if persist_items:
				self.storeItems(node, publisher, items)

			if items and not deliver_payloads:
				for item in items:
					item.children = []

			recipients = self.get_subscribers(node)
			recipients.addCallback(self.magic_filter, node, items)
			recipients.addCallback(self.pubsub_service.do_notification, node)

			return defer.succeed(None)
		except:
			f = failure.Failure()
			return defer.fail(f)

	def magic_filter(self, subscribers, node, items):
		list = {}
		for subscriber in subscribers:
			list[subscriber] = items

		return list

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

	def storeItems(self, node, publisher, items):
		for item in items:
			print "Storing item %s" % item.toXml()


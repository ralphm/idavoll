from twisted.application import service
from twisted.python import components, failure
from twisted.internet import defer, reactor
from twisted.protocols.jabber import jid

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

class Subscription:
	def __init__(self, state):
		self.state = state

class NodeConfiguration:
	def __init__(self):
		self.persist_items = False
		self.deliver_payloads = False

class Node:
	def __init__(self, name):
		self.name = name
		self.configuration = NodeConfiguration()
		self.subscriptions = {}
		self.affiliations = {}
		self.items = {}

class MemoryBackendService(service.Service):

	__implements__ = IBackendService,

	def __init__(self):
		self.nodes = {}

		node = Node("ralphm/mood/ralphm@ik.nu")
		node.subscriptions["ralphm@doe.ik.nu"] = Subscription("subscribed")
		node.affiliations["ralphm@ik.nu"] = "owner"
		node.affiliations["ralphm@doe.ik.nu"] = "publisher"
		node.configuration.persist_items = True
		node.configuration.deliver_payloads = True
		self.nodes[node.name] = node

	def do_publish(self, node_id, publisher, items):
		try:
			try:
				node = self.nodes[node_id]
				persist_items = node.configuration.persist_items
				deliver_payloads = node.configuration.deliver_payloads
			except KeyError:
				raise NodeNotFound

			try:
				if node.affiliations[publisher] not in ['owner', 'publisher']:
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

			print "publish by %s to %s" % (publisher, node_id)

			if persist_items or deliver_payloads:
				for item in items:
					if item["id"] is None:
						item["id"] = 'random'

			if persist_items:
				self.storeItems(node_id, publisher, items)

			if items and not deliver_payloads:
				for item in items:
					item.children = []

			recipients = self.get_subscribers(node_id)
			recipients.addCallback(self.magic_filter, node_id, items)
			recipients.addCallback(self.pubsub_service.do_notification, node_id)

			return defer.succeed(None)
		except:
			f = failure.Failure()
			return defer.fail(f)

	def do_subscribe(self, node_id, subscriber, requestor):
		# expect subscriber and requestor to be a jid.JID 
		try:
			try:
				node = self.nodes[node_id]
			except KeyError:
				raise NodeNotFound

			affiliation = node.affiliations.get(requestor.full(), 'none')

			if affiliation == 'banned':
				raise NotAuthorized

			print subscriber.full()
			print subscriber.userhostJID().full()
			print requestor.full()

			if subscriber.userhostJID() != requestor:
				raise NotAuthorized

			try:
				subscription = node.subscriptions[subscriber.full()]
			except KeyError:
				subscription = Subscription('subscribed')
				node.subscriptions[subscriber.full()] = subscription

			print node.subscriptions

			return defer.succeed({
					'affiliation': affiliation,
					'node': node_id,
					'jid': subscriber,
					'subscription': subscription.state})
		except:
			f = failure.Failure()
			return defer.fail(f)

		
	def magic_filter(self, subscribers, node_id, items):
		list = {}
		for subscriber in subscribers:
			list[subscriber] = items

		return list

	def get_subscribers(self, node_id):
		d = defer.Deferred()
		try:
			result = self.nodes[node_id].subscriptions.keys()
		except:
			f = failure.Failure()
			reactor.callLater(0, d.errback, f)
		else:
			reactor.callLater(0, d.callback, result)

		return d

	def storeItems(self, node_id, publisher, items):
		for item in items:
			self.nodes[node_id].items[item["id"]] = item

		print self.nodes[node_id].items

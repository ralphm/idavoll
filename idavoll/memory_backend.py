from twisted.application import service
from twisted.internet import defer
from twisted.protocols.jabber import jid
import backend

class Subscription:
	def __init__(self, state):
		self.state = state

class NodeConfiguration:
	def __init__(self):
		self.persist_items = False
		self.deliver_payloads = False

class Node:
	def __init__(self, id):
		self.id = id
		self.configuration = NodeConfiguration()
		self.subscriptions = {}
		self.affiliations = {}
		self.items = {}

class MemoryBackendService(service.Service):

	__implements__ = backend.IService,

	def __init__(self):
		self.nodes = {}

		node = Node("ralphm/mood/ralphm@ik.nu")
		node.subscriptions["ralphm@doe.ik.nu"] = Subscription("subscribed")
		node.subscriptions["notify@ik.nu/mood_monitor"] = Subscription("subscribed")
		node.affiliations["ralphm@ik.nu"] = "owner"
		node.affiliations["ralphm@doe.ik.nu"] = "publisher"
		node.configuration.persist_items = True
		node.configuration.deliver_payloads = True
		self.nodes[node.id] = node

	def do_publish(self, node_id, publisher, items):
		try:
			node = self.nodes[node_id]
			persist_items = node.configuration.persist_items
			deliver_payloads = node.configuration.deliver_payloads
		except KeyError:
			raise backend.NodeNotFound

		try:
			if node.affiliations[publisher] not in ['owner', 'publisher']:
				raise backend.NotAuthorized
		except KeyError:
			raise backend.NotAuthorized

		if items and not persist_items and not deliver_payloads:
			raise backend.NoPayloadAllowed
		elif not items and (persist_items or deliver_payloads):
			raise backend.PayloadExpected

		print "publish by %s to %s" % (publisher, node_id)

		if persist_items or deliver_payloads:
			for item in items:
				if item["id"] is None:
					item["id"] = 'random'	# FIXME

		if persist_items:
			self.storeItems(node_id, publisher, items)

		if items and not deliver_payloads:
			for item in items:
				item.children = []

		recipients = self.get_subscribers(node_id)
		recipients.addCallback(self.magic_filter, node_id, items)
		recipients.addCallback(self.pubsub_service.do_notification, node_id)

		return defer.succeed(None)

	def do_subscribe(self, node_id, subscriber, requestor):
		# expect subscriber and requestor to be a jid.JID 
		try:
			node = self.nodes[node_id]
		except KeyError:
			raise backend.NodeNotFound

		affiliation = node.affiliations.get(requestor.full(), 'none')

		if affiliation == 'banned':
			raise backend.NotAuthorized

		print subscriber.full()
		print subscriber.userhostJID().full()
		print requestor.full()

		if subscriber.userhostJID() != requestor:
			raise backend.NotAuthorized

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
		
	def magic_filter(self, subscribers, node_id, items):
		list = {}
		for subscriber in subscribers:
			list[subscriber] = items

		return list

	def get_subscribers(self, node_id):
		d = defer.Deferred()
		try:
			return defer.succeed(self.nodes[node_id].subscriptions.keys())
		except:
			return defer.fail()

	def storeItems(self, node_id, publisher, items):
		for item in items:
			self.nodes[node_id].items[item["id"]] = item

		print self.nodes[node_id].items

	def create_node(self, node_id, owner):
		result = {}

		if not node_id:
			raise backend.NoInstantNodes

		if node_id in self.nodes:
			raise backend.NodeExists
	
		node = Node(node_id)
		node.affiliations[owner.full()] = 'owner'
		self.nodes[node_id] = node

		return defer.succeed({'node_id': node.id})

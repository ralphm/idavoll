from twisted.python import components

class IService(components.Interface):
	""" Interface to a backend service of a pubsub service """

	def do_publish(self, node, publisher, item):
		""" Returns a deferred that returns """

class Error(Exception):
	msg = ''

	def __str__(self):
		return self.msg
	
class NodeNotFound(Error):
	msg = 'Node not found'

class NotAuthorized(Error):
	pass

class PayloadExpected(Error):
	msg = 'Payload expected'

class NoPayloadAllowed(Error):
	msg = 'No payload allowed'

class NoInstantNodes(Error):
	pass

class NodeExists(Error):
	pass

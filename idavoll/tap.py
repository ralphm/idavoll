from twisted.application import internet, service
from twisted.internet import interfaces
from twisted.python import usage
import idavoll

class Options(usage.Options):
	optParameters = [
		('jid', None, 'pubsub'),
		('secret', None, None),
		('rhost', None, '127.0.0.1'),
		('rport', None, '6000')
	]

def makeService(config):
	return idavoll.makeService(config)

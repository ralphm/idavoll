from twisted.application import internet, service
from twisted.internet import interfaces
from twisted.python import usage
import idavoll

class Options(usage.Options):
	optParameters = [
		('jid', None, 'pubsub'),
		('secret', None, None),
		('rhost', None, '127.0.0.1'),
		('rport', None, '6000'),
		('backend', None, 'memory'),
		('dbuser', None, ''),
		('dbname', None, 'pubsub'),
	]

	optFlags = [('verbose', 'v', 'Show traffic')]
	
	def postOptions(self):
		if self['backend'] not in ['pgsql', 'memory']:
			raise usage.UsageError, "Unknown backend!"

def makeService(config):
	return idavoll.makeService(config)

# Copyright (c) 2003-2006 Ralph Meijer
# See LICENSE for details.

from twisted.application import internet, service
from twisted.internet import interfaces
from twisted.python import usage
import idavoll

class Options(usage.Options):
	optParameters = [
		('jid', None, 'pubsub'),
		('secret', None, 'secret'),
		('rhost', None, '127.0.0.1'),
		('rport', None, '5347'),
		('backend', None, 'memory'),
		('dbuser', None, ''),
		('dbname', None, 'pubsub'),
	]

	optFlags = [
		('verbose', 'v', 'Show traffic'),
		('hide-nodes', None, 'Hide all nodes for disco')
	]
	
	def postOptions(self):
		if self['backend'] not in ['pgsql', 'memory']:
			raise usage.UsageError, "Unknown backend!"

def makeService(config):
	return idavoll.makeService(config)

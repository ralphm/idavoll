# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

"""
Example TAC for Idavoll.
"""

from twisted.application import service
from twisted.words.protocols.jabber.jid import JID

from idavoll import tap

application = service.Application("Idavoll")

config = {
    'jid': JID('pubsub.example.org'),
    'secret': 'secret',
    'rhost': '127.0.0.1',
    'rport': 5347,
    'backend': 'memory',
    'verbose': True,
    'hide-nodes': False,
}

idavollService = tap.makeService(config)
idavollService.setServiceParent(application)

# Set the maximum delay until trying to reconnect.
componentService = idavollService.getServiceNamed('component')
componentService.factory.maxdelay = 300

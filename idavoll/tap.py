# Copyright (c) 2003-2007 Ralph Meijer
# See LICENSE for details.

from twisted.application import service
from twisted.python import usage
from twisted.words.protocols.jabber.jid import JID

from wokkel.component import Component
from wokkel.disco import DiscoHandler
from wokkel.generic import FallbackHandler, VersionHandler
from wokkel.iwokkel import IPubSubService

from idavoll.backend import BackendService

__version__ = '0.6.0'

class Options(usage.Options):
    optParameters = [
        ('jid', None, 'pubsub', 'JID this component will be available at'),
        ('secret', None, 'secret', 'Jabber server component secret'),
        ('rhost', None, '127.0.0.1', 'Jabber server host'),
        ('rport', None, '5347', 'Jabber server port'),
        ('backend', None, 'memory', 'Choice of storage backend'),
        ('dbuser', None, '', 'Database user (pgsql backend)'),
        ('dbname', None, 'pubsub', 'Database name (pgsql backend)'),
        ('dbpass', None, '', 'Database password (pgsql backend)'),
        ('dbhost', None, '', 'Database host (pgsql backend)'),
        ('dbport', None, '', 'Database port (pgsql backend)'),
    ]

    optFlags = [
        ('verbose', 'v', 'Show traffic'),
        ('hide-nodes', None, 'Hide all nodes for disco')
    ]

    def postOptions(self):
        if self['backend'] not in ['pgsql', 'memory']:
            raise usage.UsageError, "Unknown backend!"

def makeService(config):
    s = service.MultiService()

    cs = Component(config["rhost"], int(config["rport"]),
                   config["jid"], config["secret"])
    cs.setServiceParent(s)

    cs.factory.maxDelay = 900

    if config["verbose"]:
        cs.logTraffic = True

    FallbackHandler().setHandlerParent(cs)
    VersionHandler('Idavoll', __version__).setHandlerParent(cs)
    DiscoHandler().setHandlerParent(cs)

    if config['backend'] == 'pgsql':
        from idavoll.pgsql_storage import Storage
        st = Storage(user=config['dbuser'],
                     database=config['dbname'],
                     password=config['dbpass'],
                     host=config['dbhost'],
                     port=config['dbport'])
    elif config['backend'] == 'memory':
        from idavoll.memory_storage import Storage
        st = Storage()

    bs = BackendService(st)
    bs.setServiceParent(s)

    ps = IPubSubService(bs)
    ps.setHandlerParent(cs)
    ps.hideNodes = config["hide-nodes"]
    ps.serviceJID = JID(config["jid"])

    return s

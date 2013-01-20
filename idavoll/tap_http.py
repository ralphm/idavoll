# Copyright (c) Ralph Meijer.
# See LICENSE for details.

from twisted.application import internet, strports
from twisted.conch import manhole, manhole_ssh
from twisted.cred import portal, checkers
from twisted.web import resource, server

from idavoll import gateway, tap
from idavoll.gateway import RemoteSubscriptionService

class Options(tap.Options):
    optParameters = [
            ('webport', None, '8086', 'Web port'),
    ]



def getManholeFactory(namespace, **passwords):
    def getManHole(_):
        return manhole.Manhole(namespace)

    realm = manhole_ssh.TerminalRealm()
    realm.chainedProtocolFactory.protocolFactory = getManHole
    p = portal.Portal(realm)
    p.registerChecker(
            checkers.InMemoryUsernamePasswordDatabaseDontUse(**passwords))
    f = manhole_ssh.ConchFactory(p)
    return f



def makeService(config):
    s = tap.makeService(config)

    bs = s.getServiceNamed('backend')
    cs = s.getServiceNamed('component')

    # Set up XMPP service for subscribing to remote nodes

    if config['backend'] == 'pgsql':
        from idavoll.pgsql_storage import GatewayStorage
        gst = GatewayStorage(bs.storage.dbpool)
    elif config['backend'] == 'memory':
        from idavoll.memory_storage import GatewayStorage
        gst = GatewayStorage()

    ss = RemoteSubscriptionService(config['jid'], gst)
    ss.setHandlerParent(cs)
    ss.startService()

    # Set up web service

    root = resource.Resource()

    # Set up resources that exposes the backend
    root.putChild('create', gateway.CreateResource(bs, config['jid'],
                                                   config['jid']))
    root.putChild('delete', gateway.DeleteResource(bs, config['jid'],
                                                   config['jid']))
    root.putChild('publish', gateway.PublishResource(bs, config['jid'],
                                                     config['jid']))
    root.putChild('list', gateway.ListResource(bs))

    # Set up resources for accessing remote pubsub nodes.
    root.putChild('subscribe', gateway.RemoteSubscribeResource(ss))
    root.putChild('unsubscribe', gateway.RemoteUnsubscribeResource(ss))
    root.putChild('items', gateway.RemoteItemsResource(ss))

    site = server.Site(root)
    w = internet.TCPServer(int(config['webport']), site)
    w.setServiceParent(s)

    # Set up a manhole

    namespace = {'service': s,
                 'component': cs,
                 'backend': bs,
                 'root': root}

    f = getManholeFactory(namespace, admin='admin')
    manholeService = strports.service('2222', f)
    manholeService.setServiceParent(s)

    return s


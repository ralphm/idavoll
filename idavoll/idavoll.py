from twisted.protocols.jabber import component
from twisted.application import service
from twisted.python import components
from twisted.internet import defer
import backend
import pubsub
import xmpp_error
import disco

import sys

NS_VERSION = 'jabber:iq:version'

IQ_GET = '/iq[@type="get"]'
IQ_SET = '/iq[@type="set"]'
VERSION = IQ_GET + '/query[@xmlns="' + NS_VERSION + '"]'
DISCO_INFO = IQ_GET + '/query[@xmlns="' + disco.NS_INFO + '"]'
DISCO_ITEMS = IQ_GET + '/query[@xmlns="' + disco.NS_ITEMS + '"]'

class IdavollService(component.Service):

    def componentConnected(self, xmlstream):
        self.xmlstream = xmlstream
        xmlstream.addObserver(VERSION, self.onVersion, 1)
        xmlstream.addObserver(DISCO_INFO, self.onDiscoInfo, 1)
        xmlstream.addObserver(DISCO_ITEMS, self.onDiscoItems, 1)
        xmlstream.addObserver(IQ_GET, self.iqFallback, -1)
        xmlstream.addObserver(IQ_SET, self.iqFallback, -1)

    def get_disco_info(self, node):
        info = []

        if not node:
            info.append(disco.Feature(disco.NS_ITEMS))
            info.append(disco.Feature(NS_VERSION))

        return defer.succeed(info)
    
    def onVersion(self, iq):
        iq.swapAttributeValues("to", "from")
        iq["type"] = "result"
        name = iq.addElement("name", None, 'Idavoll')
        version = iq.addElement("version", None, '0.1')
        self.send(iq)
        iq.handled = True

    def onDiscoInfo(self, iq):
        dl = []
        node = iq.query.getAttribute("node")

        for c in self.parent:
            if components.implements(c, component.IService):
                if hasattr(c, "get_disco_info"):
                    dl.append(c.get_disco_info(node))
        d = defer.DeferredList(dl, fireOnOneErrback=1)
        d.addCallback(self._disco_info_results, iq, node)
        d.addErrback(self._error, iq)
        d.addCallback(self.send)

        iq.handled = True

    def _disco_info_results(self, results, iq, node):
        info = []
        for i in results:
            info.extend(i[1])

        if node and not info:
            return xmpp_error.error_from_iq(iq, 'item-not-found')
        else:
            iq.swapAttributeValues("to", "from")
            iq["type"] = "result"
            iq.query.children = info

        return iq

    def _error(self, results, iq):
        return xmpp_error.error_from_iq(iq, 'internal-error')

    def onDiscoItems(self, iq):
        dl = []
        node = iq.query.getAttribute("node")

        for c in self.parent:
            if components.implements(c, component.IService):
                if hasattr(c, "get_disco_items"):
                    dl.append(c.get_disco_items(node))
        d = defer.DeferredList(dl, fireOnOneErrback=1)
        d.addCallback(self._disco_items_result, iq, node)
        d.addErrback(self._error, iq)
        d.addCallback(self.send)
        
        iq.handled = True
    
    def _disco_items_result(self, results, iq, node):
        items = []

        for i in results:
            items.extend(i[1])

        iq.swapAttributeValues("to", "from")
        iq["type"] = "result"
        iq.query.children = items

        return iq
    
    def iqFallback(self, iq):
        if iq.handled == True:
            return

        self.send(xmpp_error.error_from_iq(iq, 'service-unavailable'))

def makeService(config):
    serviceCollection = service.MultiService()

    # set up Jabber Component
    sm = component.buildServiceManager(config["jid"], config["secret"],
            ("tcp:%s:%s" % (config["rhost"], config["rport"])))

    if config['backend'] == 'pgsql':
        import pgsql_backend as b
        st = b.Storage(user=config['dbuser'], database=config['dbname'])
    elif config['backend'] == 'memory':
        import memory_backend as b
        st = b.Storage()

    bs = b.BackendService(st)

    component.IService(bs).setServiceParent(sm)

    bsc = b.PublishService()
    bsc.setServiceParent(bs)
    component.IService(bsc).setServiceParent(sm)

    bsc = b.NotificationService()
    bsc.setServiceParent(bs)
    component.IService(bsc).setServiceParent(sm)

    bsc = b.SubscriptionService()
    bsc.setServiceParent(bs)
    component.IService(bsc).setServiceParent(sm)

    bsc = b.NodeCreationService()
    bsc.setServiceParent(bs)
    component.IService(bsc).setServiceParent(sm)

    if config['backend'] == 'pgsql':
        bsc = b.AffiliationsService()
        bsc.setServiceParent(bs)
        component.IService(bsc).setServiceParent(sm)

    s = IdavollService()
    s.setServiceParent(sm)

    sm.setServiceParent(serviceCollection)

    # other stuff

    return sm

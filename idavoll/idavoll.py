from twisted.protocols.jabber import component
from twisted.application import service
from twisted.python import components
from twisted.internet import defer
import backend
import pubsub
import xmpp_error

import sys

NS_DISCO = 'http://jabber.org/protocol/disco'
NS_DISCO_INFO = NS_DISCO + '#info'
NS_DISCO_ITEMS = NS_DISCO + '#items'
NS_VERSION = 'jabber:iq:version'

IQ_GET = '/iq[@type="get"]'
IQ_SET = '/iq[@type="set"]'
VERSION = IQ_GET + '/query[@xmlns="' + NS_VERSION + '"]'
DISCO_INFO = IQ_GET + '/query[@xmlns="' + NS_DISCO_INFO + '"]'
DISCO_ITEMS = IQ_GET + '/query[@xmlns="' + NS_DISCO_ITEMS + '"]'

class IdavollService(component.Service):

    def componentConnected(self, xmlstream):
        self.xmlstream = xmlstream
        xmlstream.addObserver(VERSION, self.onVersion, 1)
        xmlstream.addObserver(DISCO_INFO, self.onDiscoInfo, 1)
        xmlstream.addObserver(DISCO_ITEMS, self.onDiscoItems, 1)
        xmlstream.addObserver(IQ_GET, self.iqFallback, -1)
        xmlstream.addObserver(IQ_SET, self.iqFallback, -1)

    def getFeatures(self, node):
        features = []

        if not node:
            features.extend([NS_DISCO_ITEMS, NS_VERSION])

        return defer.succeed(features)
    
    def onVersion(self, iq):
        iq.swapAttributeValues("to", "from")
        iq["type"] = "result"
        name = iq.addElement("name", None, 'Idavoll')
        version = iq.addElement("version", None, '0.1')
        self.send(iq)
        iq.handled = True

    def onDiscoInfo(self, iq):
        identities_deferreds = []
        features_deferreds = []
        node = iq.query.getAttribute("node")

        for c in self.parent:
            if components.implements(c, component.IService):
                if hasattr(c, "getIdentities"):
                    identities_deferreds.append(c.getIdentities(node))
                if hasattr(c, "getFeatures"):
                    features_deferreds.append(c.getFeatures(node))
        print identities_deferreds
        print features_deferreds
        d1 = defer.DeferredList(identities_deferreds, fireOnOneErrback=1)
        d2 = defer.DeferredList(features_deferreds, fireOnOneErrback=1)
        d = defer.DeferredList([d1, d2], fireOnOneErrback=1)
        d.addCallback(self._disco_info_results, iq, node)
        d.addErrback(self._disco_info_error, iq)
        d.addCallback(self.q)
        d.addCallback(self.send)

        iq.handled = True

    def q(self, result):
        print result
        return result

    def _disco_info_results(self, results, iq, node):
        identities = []
        for i in results[0][1]:
            identities.extend(i[1])

        features = []
        for f in results[1][1]:
            features.extend(f[1])

        if node and not features and not identities:
            return xmpp_error.error_from_iq(iq, 'item-not-found')
        else:
            iq.swapAttributeValues("to", "from")
            iq["type"] = "result"
            for identity in identities:
                i = iq.query.addElement("identity")
                i.attributes = identity
            print features
            for feature in features:
                f = iq.query.addElement("feature")
                f["var"] = feature


        return iq

    def _disco_info_error(self, results, iq):
        return xmpp_error.error_from_iq(iq, 'internal-error')

    def onDiscoItems(self, iq):
        iq.swapAttributeValues("to", "from")
        iq["type"] = "result"
        iq.query.children = []
        self.send(iq)
    
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

# Copyright (c) 2003-2009 Ralph Meijer
# See LICENSE for details.

"""
Tests for L{idavoll.backend}.
"""

from zope.interface import implements
from zope.interface.verify import verifyObject

from twisted.internet import defer
from twisted.trial import unittest
from twisted.words.protocols.jabber import jid
from twisted.words.protocols.jabber.error import StanzaError

from wokkel import iwokkel, pubsub

from idavoll import backend, error, iidavoll

OWNER = jid.JID('owner@example.com')
SERVICE = jid.JID('test.example.org')
NS_PUBSUB = 'http://jabber.org/protocol/pubsub'

class BackendTest(unittest.TestCase):

    def test_interfaceIBackend(self):
        self.assertTrue(verifyObject(iidavoll.IBackendService,
                                     backend.BackendService(None)))


    def test_deleteNode(self):
        class TestNode:
            nodeIdentifier = 'to-be-deleted'
            def getAffiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')

        class TestStorage:
            def __init__(self):
                self.deleteCalled = []

            def getNode(self, nodeIdentifier):
                return defer.succeed(TestNode())

            def deleteNode(self, nodeIdentifier):
                if nodeIdentifier in ['to-be-deleted']:
                    self.deleteCalled.append(nodeIdentifier)
                    return defer.succeed(None)
                else:
                    return defer.fail(error.NodeNotFound())

        def preDelete(data):
            self.assertFalse(self.storage.deleteCalled)
            preDeleteCalled.append(data)
            return defer.succeed(None)

        def cb(result):
            self.assertEquals(1, len(preDeleteCalled))
            data = preDeleteCalled[-1]
            self.assertEquals('to-be-deleted', data['nodeIdentifier'])
            self.assertTrue(self.storage.deleteCalled)

        self.storage = TestStorage()
        self.backend = backend.BackendService(self.storage)

        preDeleteCalled = []

        self.backend.registerPreDelete(preDelete)
        d = self.backend.deleteNode('to-be-deleted', OWNER)
        d.addCallback(cb)
        return d


    def test_deleteNodeRedirect(self):
        uri = 'xmpp:%s?;node=test2' % (SERVICE.full(),)

        class TestNode:
            nodeIdentifier = 'to-be-deleted'
            def getAffiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')

        class TestStorage:
            def __init__(self):
                self.deleteCalled = []

            def getNode(self, nodeIdentifier):
                return defer.succeed(TestNode())

            def deleteNode(self, nodeIdentifier):
                if nodeIdentifier in ['to-be-deleted']:
                    self.deleteCalled.append(nodeIdentifier)
                    return defer.succeed(None)
                else:
                    return defer.fail(error.NodeNotFound())

        def preDelete(data):
            self.assertFalse(self.storage.deleteCalled)
            preDeleteCalled.append(data)
            return defer.succeed(None)

        def cb(result):
            self.assertEquals(1, len(preDeleteCalled))
            data = preDeleteCalled[-1]
            self.assertEquals('to-be-deleted', data['nodeIdentifier'])
            self.assertEquals(uri, data['redirectURI'])
            self.assertTrue(self.storage.deleteCalled)

        self.storage = TestStorage()
        self.backend = backend.BackendService(self.storage)

        preDeleteCalled = []

        self.backend.registerPreDelete(preDelete)
        d = self.backend.deleteNode('to-be-deleted', OWNER, redirectURI=uri)
        d.addCallback(cb)
        return d


    def test_createNodeNoID(self):
        """
        Test creation of a node without a given node identifier.
        """
        class TestStorage:
            def getDefaultConfiguration(self, nodeType):
                return {}

            def createNode(self, nodeIdentifier, requestor, config):
                self.nodeIdentifier = nodeIdentifier
                return defer.succeed(None)

        self.storage = TestStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        def checkID(nodeIdentifier):
            self.assertNotIdentical(None, nodeIdentifier)
            self.assertIdentical(self.storage.nodeIdentifier, nodeIdentifier)

        d = self.backend.createNode(None, OWNER)
        d.addCallback(checkID)
        return d

    class NodeStore:
        """
        I just store nodes to pose as an L{IStorage} implementation.
        """
        def __init__(self, nodes):
            self.nodes = nodes

        def getNode(self, nodeIdentifier):
            try:
                return defer.succeed(self.nodes[nodeIdentifier])
            except KeyError:
                return defer.fail(error.NodeNotFound())


    def test_getNotifications(self):
        """
        Ensure subscribers show up in the notification list.
        """
        item = pubsub.Item()
        sub = pubsub.Subscription('test', OWNER, 'subscribed')

        class TestNode:
            def getSubscriptions(self, state=None):
                return [sub]

        def cb(result):
            self.assertEquals(1, len(result))
            subscriber, subscriptions, items = result[-1]

            self.assertEquals(OWNER, subscriber)
            self.assertEquals(set([sub]), subscriptions)
            self.assertEquals([item], items)

        self.storage = self.NodeStore({'test': TestNode()})
        self.backend = backend.BackendService(self.storage)
        d = self.backend.getNotifications('test', [item])
        d.addCallback(cb)
        return d

    def test_getNotificationsRoot(self):
        """
        Ensure subscribers to the root node show up in the notification list
        for leaf nodes.

        This assumes a flat node relationship model with exactly one collection
        node: the root node. Each leaf node is automatically a child node
        of the root node.
        """
        item = pubsub.Item()
        subRoot = pubsub.Subscription('', OWNER, 'subscribed')

        class TestNode:
            def getSubscriptions(self, state=None):
                return []

        class TestRootNode:
            def getSubscriptions(self, state=None):
                return [subRoot]

        def cb(result):
            self.assertEquals(1, len(result))
            subscriber, subscriptions, items = result[-1]
            self.assertEquals(OWNER, subscriber)
            self.assertEquals(set([subRoot]), subscriptions)
            self.assertEquals([item], items)

        self.storage = self.NodeStore({'test': TestNode(),
                                       '': TestRootNode()})
        self.backend = backend.BackendService(self.storage)
        d = self.backend.getNotifications('test', [item])
        d.addCallback(cb)
        return d


    def test_getNotificationsMultipleNodes(self):
        """
        Ensure that entities that subscribe to a leaf node as well as the
        root node get exactly one notification.
        """
        item = pubsub.Item()
        sub = pubsub.Subscription('test', OWNER, 'subscribed')
        subRoot = pubsub.Subscription('', OWNER, 'subscribed')

        class TestNode:
            def getSubscriptions(self, state=None):
                return [sub]

        class TestRootNode:
            def getSubscriptions(self, state=None):
                return [subRoot]

        def cb(result):
            self.assertEquals(1, len(result))
            subscriber, subscriptions, items = result[-1]

            self.assertEquals(OWNER, subscriber)
            self.assertEquals(set([sub, subRoot]), subscriptions)
            self.assertEquals([item], items)

        self.storage = self.NodeStore({'test': TestNode(),
                                       '': TestRootNode()})
        self.backend = backend.BackendService(self.storage)
        d = self.backend.getNotifications('test', [item])
        d.addCallback(cb)
        return d


    def test_getDefaultConfiguration(self):
        """
        L{backend.BackendService.getDefaultConfiguration} should return
        a deferred that fires a dictionary with configuration values.
        """

        class TestStorage:
            def getDefaultConfiguration(self, nodeType):
                return {
                    "pubsub#persist_items": True,
                    "pubsub#deliver_payloads": True}

        def cb(options):
            self.assertIn("pubsub#persist_items", options)
            self.assertEqual(True, options["pubsub#persist_items"])

        self.backend = backend.BackendService(TestStorage())
        d = self.backend.getDefaultConfiguration('leaf')
        d.addCallback(cb)
        return d


    def test_getNodeConfiguration(self):
        class testNode:
            nodeIdentifier = 'node'
            def getConfiguration(self):
                return {'pubsub#deliver_payloads': True,
                        'pubsub#persist_items': False}

        class testStorage:
            def getNode(self, nodeIdentifier):
                return defer.succeed(testNode())

        def cb(options):
            self.assertIn("pubsub#deliver_payloads", options)
            self.assertEqual(True, options["pubsub#deliver_payloads"])
            self.assertIn("pubsub#persist_items", options)
            self.assertEqual(False, options["pubsub#persist_items"])

        self.storage = testStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        d = self.backend.getNodeConfiguration('node')
        d.addCallback(cb)
        return d


    def test_setNodeConfiguration(self):
        class testNode:
            nodeIdentifier = 'node'
            def getAffiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')
            def setConfiguration(self, options):
                self.options = options

        class testStorage:
            def __init__(self):
                self.nodes = {'node': testNode()}
            def getNode(self, nodeIdentifier):
                return defer.succeed(self.nodes[nodeIdentifier])

        def checkOptions(node):
            options = node.options
            self.assertIn("pubsub#deliver_payloads", options)
            self.assertEqual(True, options["pubsub#deliver_payloads"])
            self.assertIn("pubsub#persist_items", options)
            self.assertEqual(False, options["pubsub#persist_items"])

        def cb(result):
            d = self.storage.getNode('node')
            d.addCallback(checkOptions)
            return d

        self.storage = testStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        options = {'pubsub#deliver_payloads': True,
                   'pubsub#persist_items': False}

        d = self.backend.setNodeConfiguration('node', options, OWNER)
        d.addCallback(cb)
        return d


    def test_publishNoID(self):
        """
        Test publish request with an item without a node identifier.
        """
        class TestNode:
            nodeType = 'leaf'
            nodeIdentifier = 'node'
            def getAffiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')
            def getConfiguration(self):
                return {'pubsub#deliver_payloads': True,
                        'pubsub#persist_items': False}

        class TestStorage:
            def getNode(self, nodeIdentifier):
                return defer.succeed(TestNode())

        def checkID(notification):
            self.assertNotIdentical(None, notification['items'][0]['id'])

        self.storage = TestStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        self.backend.registerNotifier(checkID)

        items = [pubsub.Item()]
        d = self.backend.publish('node', items, OWNER)
        return d


    def test_notifyOnSubscription(self):
        """
        Test notification of last published item on subscription.
        """
        ITEM = "<item xmlns='%s' id='1'/>" % NS_PUBSUB

        class TestNode:
            implements(iidavoll.ILeafNode)
            nodeIdentifier = 'node'
            nodeType = 'leaf'
            def getAffiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')
            def getConfiguration(self):
                return {'pubsub#deliver_payloads': True,
                        'pubsub#persist_items': False,
                        'pubsub#send_last_published_item': 'on_sub'}
            def getItems(self, maxItems):
                return [ITEM]
            def addSubscription(self, subscriber, state, options):
                self.subscription = pubsub.Subscription('node', subscriber,
                                                        state, options)
                return defer.succeed(None)
            def getSubscription(self, subscriber):
                return defer.succeed(self.subscription)

        class TestStorage:
            def getNode(self, nodeIdentifier):
                return defer.succeed(TestNode())

        def cb(data):
            self.assertEquals('node', data['nodeIdentifier'])
            self.assertEquals([ITEM], data['items'])
            self.assertEquals(OWNER, data['subscription'].subscriber)

        self.storage = TestStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        d1 = defer.Deferred()
        d1.addCallback(cb)
        self.backend.registerNotifier(d1.callback)
        d2 = self.backend.subscribe('node', OWNER, OWNER)
        return defer.gatherResults([d1, d2])

    test_notifyOnSubscription.timeout = 2



class BaseTestBackend(object):
    """
    Base class for backend stubs.
    """

    def supportsPublisherAffiliation(self):
        return True


    def supportsOutcastAffiliation(self):
        return True


    def supportsPersistentItems(self):
        return True


    def supportsInstantNodes(self):
        return True


    def registerNotifier(self, observerfn, *args, **kwargs):
        return


    def registerPreDelete(self, preDeleteFn):
        return



class PubSubServiceFromBackendTest(unittest.TestCase):

    def test_interfaceIBackend(self):
        s = backend.PubSubServiceFromBackend(BaseTestBackend())
        self.assertTrue(verifyObject(iwokkel.IPubSubService, s))


    def test_preDelete(self):
        """
        Test pre-delete sending out notifications to subscribers.
        """

        class TestBackend(BaseTestBackend):
            preDeleteFn = None

            def registerPreDelete(self, preDeleteFn):
                self.preDeleteFn = preDeleteFn

            def getSubscribers(self, nodeIdentifier):
                return defer.succeed([OWNER])

        def notifyDelete(service, nodeIdentifier, subscribers,
                         redirectURI=None):
            self.assertEqual(SERVICE, service)
            self.assertEqual('test', nodeIdentifier)
            self.assertEqual([OWNER], subscribers)
            self.assertIdentical(None, redirectURI)
            d1.callback(None)

        d1 = defer.Deferred()
        s = backend.PubSubServiceFromBackend(TestBackend())
        s.serviceJID = SERVICE
        s.notifyDelete = notifyDelete
        self.assertTrue(verifyObject(iwokkel.IPubSubService, s))
        self.assertNotIdentical(None, s.backend.preDeleteFn)
        data = {'nodeIdentifier': 'test'}
        d2 = s.backend.preDeleteFn(data)
        return defer.DeferredList([d1, d2], fireOnOneErrback=1)


    def test_preDeleteRedirect(self):
        """
        Test pre-delete sending out notifications to subscribers.
        """

        uri = 'xmpp:%s?;node=test2' % (SERVICE.full(),)

        class TestBackend(BaseTestBackend):
            preDeleteFn = None

            def registerPreDelete(self, preDeleteFn):
                self.preDeleteFn = preDeleteFn

            def getSubscribers(self, nodeIdentifier):
                return defer.succeed([OWNER])

        def notifyDelete(service, nodeIdentifier, subscribers,
                         redirectURI=None):
            self.assertEqual(SERVICE, service)
            self.assertEqual('test', nodeIdentifier)
            self.assertEqual([OWNER], subscribers)
            self.assertEqual(uri, redirectURI)
            d1.callback(None)

        d1 = defer.Deferred()
        s = backend.PubSubServiceFromBackend(TestBackend())
        s.serviceJID = SERVICE
        s.notifyDelete = notifyDelete
        self.assertTrue(verifyObject(iwokkel.IPubSubService, s))
        self.assertNotIdentical(None, s.backend.preDeleteFn)
        data = {'nodeIdentifier': 'test',
                'redirectURI': uri}
        d2 = s.backend.preDeleteFn(data)
        return defer.DeferredList([d1, d2], fireOnOneErrback=1)


    def test_unsubscribeNotSubscribed(self):
        """
        Test unsubscription request when not subscribed.
        """

        class TestBackend(BaseTestBackend):
            def unsubscribe(self, nodeIdentifier, subscriber, requestor):
                return defer.fail(error.NotSubscribed())

        def cb(e):
            self.assertEquals('unexpected-request', e.condition)

        s = backend.PubSubServiceFromBackend(TestBackend())
        d = s.unsubscribe(OWNER, SERVICE, 'test', OWNER)
        self.assertFailure(d, StanzaError)
        d.addCallback(cb)
        return d


    def test_getNodeInfo(self):
        """
        Test retrieving node information.
        """

        class TestBackend(BaseTestBackend):
            def getNodeType(self, nodeIdentifier):
                return defer.succeed('leaf')

            def getNodeMetaData(self, nodeIdentifier):
                return defer.succeed({'pubsub#persist_items': True})

        def cb(info):
            self.assertIn('type', info)
            self.assertEquals('leaf', info['type'])
            self.assertIn('meta-data', info)
            self.assertEquals({'pubsub#persist_items': True}, info['meta-data'])

        s = backend.PubSubServiceFromBackend(TestBackend())
        d = s.getNodeInfo(OWNER, SERVICE, 'test')
        d.addCallback(cb)
        return d


    def test_getConfigurationOptions(self):
        class TestBackend(BaseTestBackend):
            nodeOptions = {
                    "pubsub#persist_items":
                        {"type": "boolean",
                         "label": "Persist items to storage"},
                    "pubsub#deliver_payloads":
                        {"type": "boolean",
                         "label": "Deliver payloads with event notifications"}
            }

        s = backend.PubSubServiceFromBackend(TestBackend())
        options = s.getConfigurationOptions()
        self.assertIn("pubsub#persist_items", options)


    def test_getDefaultConfiguration(self):
        class TestBackend(BaseTestBackend):
            def getDefaultConfiguration(self, nodeType):
                options = {"pubsub#persist_items": True,
                           "pubsub#deliver_payloads": True,
                           "pubsub#send_last_published_item": 'on_sub',
                }
                return defer.succeed(options)

        def cb(options):
            self.assertEquals(True, options["pubsub#persist_items"])

        s = backend.PubSubServiceFromBackend(TestBackend())
        d = s.getDefaultConfiguration(OWNER, SERVICE, 'leaf')
        d.addCallback(cb)
        return d

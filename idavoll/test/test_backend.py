# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

"""
Tests for L{idavoll.backend}.
"""

from twisted.internet import defer
from twisted.trial import unittest
from twisted.words.protocols.jabber import jid
from twisted.words.protocols.jabber.error import StanzaError

from wokkel import pubsub

from idavoll import backend, error

OWNER = jid.JID('owner@example.com')
NS_PUBSUB = 'http://jabber.org/protocol/pubsub'

class BackendTest(unittest.TestCase):
    def test_deleteNode(self):
        class testNode:
            nodeIdentifier = 'to-be-deleted'
            def getAffiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')

        class testStorage:
            def getNode(self, nodeIdentifier):
                return defer.succeed(testNode())

            def deleteNode(self, nodeIdentifier):
                if nodeIdentifier in ['to-be-deleted']:
                    self.deleteCalled = True
                    return defer.succeed(None)
                else:
                    return defer.fail(error.NodeNotFound())

        def preDelete(nodeIdentifier):
            self.preDeleteCalled = True
            return defer.succeed(None)

        def cb(result):
            self.assertTrue(self.preDeleteCalled)
            self.assertTrue(self.storage.deleteCalled)

        self.storage = testStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        self.preDeleteCalled = False
        self.deleteCalled = False

        self.backend.registerPreDelete(preDelete)
        d = self.backend.deleteNode('to-be-deleted', OWNER)
        d.addCallback(cb)
        return d


    def test_createNodeNoID(self):
        """
        Test creation of a node without a given node identifier.
        """
        class testStorage:
            def createNode(self, nodeIdentifier, requestor):
                self.nodeIdentifier = nodeIdentifier
                return defer.succeed(None)

        self.storage = testStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        def checkID(nodeIdentifier):
            self.assertNotIdentical(None, nodeIdentifier)
            self.assertIdentical(self.storage.nodeIdentifier, nodeIdentifier)

        d = self.backend.createNode(None, OWNER)
        d.addCallback(checkID)
        return d


    def test_publishNoID(self):
        """
        Test publish request with an item without a node identifier.
        """
        class testNode:
            nodeIdentifier = 'node'
            def getAffiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')
            def getConfiguration(self):
                return {'pubsub#deliver_payloads': True,
                        'pubsub#persist_items': False}

        class testStorage:
            def getNode(self, nodeIdentifier):
                return defer.succeed(testNode())

        def checkID(notification):
            self.assertNotIdentical(None, notification['items'][0]['id'])

        self.storage = testStorage()
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

        class testNode:
            nodeIdentifier = 'node'
            def getAffiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')
            def getConfiguration(self):
                return {'pubsub#deliver_payloads': True,
                        'pubsub#persist_items': False,
                        'pubsub#send_last_published_item': 'on_sub'}
            def getItems(self, maxItems):
                return [ITEM]
            def addSubscription(self, subscriber, state):
                return defer.succeed(None)

        class testStorage:
            def getNode(self, nodeIdentifier):
                return defer.succeed(testNode())

        def cb(data):
            self.assertEquals('node', data['nodeIdentifier'])
            self.assertEquals([ITEM], data['items'])
            self.assertEquals(OWNER, data['subscriber'])

        self.storage = testStorage()
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
        d = s.unsubscribe(OWNER, 'test.example.org', 'test', OWNER)
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
        d = s.getNodeInfo(OWNER, 'test.example.org', 'test')
        d.addCallback(cb)
        return d

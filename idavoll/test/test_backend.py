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

class BackendTest(unittest.TestCase):
    def test_delete_node(self):
        class testNode:
            id = 'to-be-deleted'
            def get_affiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')

        class testStorage:
            def get_node(self, node_id):
                return defer.succeed(testNode())

            def delete_node(self, node_id):
                if node_id in ['to-be-deleted']:
                    self.delete_called = True
                    return defer.succeed(None)
                else:
                    return defer.fail(error.NodeNotFound())

        def pre_delete(node_id):
            self.pre_delete_called = True
            return defer.succeed(None)

        def cb(result):
            self.assertTrue(self.pre_delete_called)
            self.assertTrue(self.storage.delete_called)

        self.storage = testStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        self.pre_delete_called = False
        self.delete_called = False

        self.backend.register_pre_delete(pre_delete)
        d = self.backend.delete_node('to-be-deleted', OWNER)
        d.addCallback(cb)
        return d

    def test_create_nodeNoID(self):
        """
        Test creation of a node without a given node identifier.
        """
        class testStorage:
            def create_node(self, node_id, requestor):
                self.node_id = node_id
                return defer.succeed(None)

        self.storage = testStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        def checkID(nodeIdentifier):
            self.assertNotIdentical(None, nodeIdentifier)
            self.assertIdentical(self.storage.node_id, nodeIdentifier)

        d = self.backend.create_node(None, OWNER)
        d.addCallback(checkID)
        return d

    def test_publishNoID(self):
        """
        Test publish request with an item without a node identifier.
        """
        class testNode:
            id = 'node'
            def get_affiliation(self, entity):
                if entity is OWNER:
                    return defer.succeed('owner')
            def get_configuration(self):
                return {'pubsub#deliver_payloads': True,
                        'pubsub#persist_items': False}

        class testStorage:
            def get_node(self, node_id):
                return defer.succeed(testNode())

        def checkID(notification):
            self.assertNotIdentical(None, notification['items'][0]['id'])

        self.storage = testStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        self.backend.register_notifier(checkID)

        items = [pubsub.Item()]
        d = self.backend.publish('node', items, OWNER)
        return d


class PubSubServiceFromBackendTest(unittest.TestCase):

    def test_unsubscribeNotSubscribed(self):
        """
        Test unsubscription request when not subscribed.
        """

        class TestBackend(object):
            def supports_publisher_affiliation(self):
                return True

            def supports_outcast_affiliation(self):
                return True

            def supports_persistent_items(self):
                return True

            def supports_instant_nodes(self):
                return True

            def register_notifier(self, observerfn, *args, **kwargs):
                return

            def unsubscribe(self, nodeIdentifier, subscriber, requestor):
                return defer.fail(error.NotSubscribed())

        def cb(e):
            self.assertEquals('unexpected-request', e.condition)

        s = backend.PubSubServiceFromBackend(TestBackend())
        d = s.unsubscribe(OWNER, 'test.example.org', 'test', OWNER)
        self.assertFailure(d, StanzaError)
        d.addCallback(cb)
        return d

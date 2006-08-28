# Copyright (c) 2003-2006 Ralph Meijer
# See LICENSE for details.

from twisted.trial import unittest
from zope.interface import implements
from twisted.internet import defer
from twisted.words.protocols.jabber import jid

from idavoll import backend, storage

OWNER = jid.JID('owner@example.com')

class testNode:
    id = 'to-be-deleted'
    def get_affiliation(self, entity):
        if entity is OWNER:
            return defer.succeed('owner')

class testStorage:

    implements(storage.IStorage)

    def get_node(self, node_id):
        return defer.succeed(testNode())

    def delete_node(self, node_id):
        if node_id in ['to-be-deleted']:
            self.backend.delete_called = True
            return defer.succeed(None)
        else:
            return defer.fail(storage.NodeNotFound())

class NodeDeletionServiceTests:
    pre_delete_called = False
    delete_called = False

    def setUpClass(self):
        self.storage = testStorage()
        self.storage.backend = self

    def testDeleteNode(self):
        def pre_delete(node_id):
            self.pre_delete_called = True
            return defer.succeed(None)

        def cb(result):
            self.assert_(self.pre_delete_called)
            self.assert_(self.delete_called)

        self.backend.register_pre_delete(pre_delete)
        d = self.backend.delete_node('to-be-deleted', OWNER)
        d.addCallback(cb)

class GenericNodeDeletionServiceTestCase(unittest.TestCase,
                                         NodeDeletionServiceTests):

    def setUpClass(self):
        NodeDeletionServiceTests.setUpClass(self)
        from idavoll.generic_backend import BackendService, NodeDeletionService
        bs = BackendService(self.storage)
        self.backend = NodeDeletionService()
        self.backend.setServiceParent(bs)

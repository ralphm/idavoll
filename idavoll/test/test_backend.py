# Copyright (c) 2003-2007 Ralph Meijer
# See LICENSE for details.

"""
Tests for L{idavoll.backend}.
"""

from twisted.trial import unittest
from zope.interface import implements
from twisted.internet import defer
from twisted.words.protocols.jabber import jid

from idavoll import backend, error, iidavoll

OWNER = jid.JID('owner@example.com')

class testNode:
    id = 'to-be-deleted'
    def get_affiliation(self, entity):
        if entity is OWNER:
            return defer.succeed('owner')

class testStorage:

    implements(iidavoll.IStorage)

    def get_node(self, node_id):
        return defer.succeed(testNode())

    def delete_node(self, node_id):
        if node_id in ['to-be-deleted']:
            self.delete_called = True
            return defer.succeed(None)
        else:
            return defer.fail(error.NodeNotFound())

class BackendTest(unittest.TestCase):
    def setUp(self):
        self.storage = testStorage()
        self.backend = backend.BackendService(self.storage)
        self.storage.backend = self.backend

        self.pre_delete_called = False
        self.delete_called = False

    def testDeleteNode(self):
        def pre_delete(node_id):
            self.pre_delete_called = True
            return defer.succeed(None)

        def cb(result):
            self.assertTrue(self.pre_delete_called)
            self.assertTrue(self.storage.delete_called)

        self.backend.register_pre_delete(pre_delete)
        d = self.backend.delete_node('to-be-deleted', OWNER)
        d.addCallback(cb)
        return d

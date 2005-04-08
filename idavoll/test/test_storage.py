from twisted.trial import unittest
from twisted.trial.assertions import *
from twisted.words.protocols.jabber import jid

from idavoll import storage

OWNER = jid.JID('owner@example.com')
SUBSCRIBER = jid.JID('subscriber@example.com/Home')

class StorageTests:

    def _assignTestNode(self, node):
        self.node = node

    def setUpClass(self):
        d = self.s.get_node('pre-existing')
        d.addCallback(self._assignTestNode)
        return d

    def testGetNode(self):
        return self.s.get_node('pre-existing')

    def testGetNonExistingNode(self):
        d = self.s.get_node('non-existing')
        assertFailure(d, storage.NodeNotFound)
        return d

    def testGetNodeIDs(self):
        def cb(node_ids):
            assertIn('pre-existing', node_ids)
            assertNotIn('non-existing', node_ids)

        return self.s.get_node_ids().addCallback(cb)

    def testCreateExistingNode(self):
        d = self.s.create_node('pre-existing', OWNER)
        assertFailure(d, storage.NodeExists)
        return d

    def testCreateNode(self):
        def cb(void):
            d = self.s.get_node('new 1')
            return d

        d = self.s.create_node('new 1', OWNER)
        d.addCallback(cb)
        return d

    def testDeleteNonExistingNode(self):
        d = self.s.delete_node('non-existing')
        assertFailure(d, storage.NodeNotFound)
        return d

    def testDeleteNode(self):
        def cb(void):
            d = self.s.get_node('to-be-deleted')
            assertFailure(d, storage.NodeNotFound)
            return d

        d = self.s.delete_node('to-be-deleted')
        d.addCallback(cb)
        return d

    def testGetAffiliations(self):
        def cb(affiliations):
            assertIn(('pre-existing', 'owner'), affiliations)

        d = self.s.get_affiliations(OWNER)
        d.addCallback(cb)
        return d

    def testGetSubscriptions(self):
        def cb(subscriptions):
            assertIn(('pre-existing', SUBSCRIBER, 'subscribed'), subscriptions)
        
        d = self.s.get_subscriptions(SUBSCRIBER)
        d.addCallback(cb)
        return d

    # Node tests

    def testGetType(self):
        assertEqual(self.node.get_type(), 'leaf')

    def testGetConfiguration(self):
        config = self.node.get_configuration()
        assertIn('pubsub#persist_items', config.iterkeys())
        assertIn('pubsub#deliver_payloads', config.iterkeys())
        assertEqual(config['pubsub#persist_items'], True)
        assertEqual(config['pubsub#deliver_payloads'], True)

    def testGetMetaData(self):
        meta_data = self.node.get_meta_data()
        for key, value in self.node.get_configuration().iteritems():
            assertIn(key, meta_data.iterkeys())
            assertEqual(value, meta_data[key])
        assertIn('pubsub#node_type', meta_data.iterkeys())
        assertEqual(meta_data['pubsub#node_type'], 'leaf')


class MemoryStorageStorageTestCase(unittest.TestCase, StorageTests):

    def setUpClass(self):
        from idavoll.memory_storage import Storage, LeafNode, Subscription, \
                                           default_config
        self.s = Storage()
        self.s._nodes['pre-existing'] = LeafNode('pre-existing', OWNER,
                                                 default_config)
        self.s._nodes['to-be-deleted'] = LeafNode('to-be-deleted', OWNER, None)
        self.s._nodes['pre-existing']._subscriptions[SUBSCRIBER.full()] = \
                Subscription('subscribed')

        return StorageTests.setUpClass(self)

class PgsqlStorageStorageTestCase(unittest.TestCase, StorageTests):
    def _callSuperSetUpClass(self, void):
        return StorageTests.setUpClass(self)

    def setUpClass(self):
        from idavoll.pgsql_storage import Storage
        self.s = Storage('ralphm', 'pubsub_test')
        self.s._dbpool.start()
        d = self.s._dbpool.runInteraction(self.init)
        d.addCallback(self._callSuperSetUpClass)
        return d

    def tearDownClass(self):
        return self.s._dbpool.runInteraction(self.cleandb)

    def init(self, cursor):
        self.cleandb(cursor)
        cursor.execute("""INSERT INTO nodes (node) VALUES ('pre-existing')""")
        cursor.execute("""INSERT INTO nodes (node) VALUES ('to-be-deleted')""")
        cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                       OWNER.userhost().encode('utf-8'))
        cursor.execute("""INSERT INTO affiliations
                          (node_id, entity_id, affiliation)
                          SELECT nodes.id, entities.id, 'owner'
                          FROM nodes, entities
                          WHERE node='pre-existing' AND jid=%s""",
                       OWNER.userhost().encode('utf-8'))
        cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                       SUBSCRIBER.userhost().encode('utf-8'))
        cursor.execute("""INSERT INTO subscriptions
                          (node_id, entity_id, resource, subscription)
                          SELECT nodes.id, entities.id, %s, 'subscribed'
                          FROM nodes, entities
                          WHERE node='pre-existing' AND jid=%s""",
                       (SUBSCRIBER.resource.encode('utf-8'),
                        SUBSCRIBER.userhost().encode('utf-8')))
    
    def cleandb(self, cursor):
        cursor.execute("""DELETE FROM nodes WHERE node in
                          ('non-existing', 'pre-existing', 'to-be-deleted',
                           'new 1', 'new 2', 'new 3')""")
        cursor.execute("""DELETE FROM entities WHERE jid=%s""",
                       OWNER.userhost().encode('utf-8'))
        cursor.execute("""DELETE FROM entities WHERE jid=%s""",
                       SUBSCRIBER.userhost().encode('utf-8'))

# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

"""
Tests for L{idavoll.memory_storage} and L{idavoll.pgsql_storage}.
"""

from twisted.trial import unittest
from twisted.words.protocols.jabber import jid
from twisted.internet import defer
from twisted.words.xish import domish

from wokkel import pubsub

from idavoll import error

OWNER = jid.JID('owner@example.com')
SUBSCRIBER = jid.JID('subscriber@example.com/Home')
SUBSCRIBER_NEW = jid.JID('new@example.com/Home')
SUBSCRIBER_TO_BE_DELETED = jid.JID('to_be_deleted@example.com/Home')
SUBSCRIBER_PENDING = jid.JID('pending@example.com/Home')
PUBLISHER = jid.JID('publisher@example.com')
ITEM = domish.Element((pubsub.NS_PUBSUB, 'item'), pubsub.NS_PUBSUB)
ITEM['id'] = 'current'
ITEM.addElement(('testns', 'test'), content=u'Test \u2083 item')
ITEM_NEW = domish.Element((pubsub.NS_PUBSUB, 'item'), pubsub.NS_PUBSUB)
ITEM_NEW['id'] = 'new'
ITEM_NEW.addElement(('testns', 'test'), content=u'Test \u2083 item')
ITEM_UPDATED = domish.Element((pubsub.NS_PUBSUB, 'item'), pubsub.NS_PUBSUB)
ITEM_UPDATED['id'] = 'current'
ITEM_UPDATED.addElement(('testns', 'test'), content=u'Test \u2084 item')
ITEM_TO_BE_DELETED = domish.Element((pubsub.NS_PUBSUB, 'item'),
                                    pubsub.NS_PUBSUB)
ITEM_TO_BE_DELETED['id'] = 'to-be-deleted'
ITEM_TO_BE_DELETED.addElement(('testns', 'test'), content=u'Test \u2083 item')

def decode(object):
    if isinstance(object, str):
        object = object.decode('utf-8')
    return object


class StorageTests:

    def _assignTestNode(self, node):
        self.node = node

    def setUp(self):
        d = self.s.get_node('pre-existing')
        d.addCallback(self._assignTestNode)
        return d

    def testGetNode(self):
        return self.s.get_node('pre-existing')

    def testGetNonExistingNode(self):
        d = self.s.get_node('non-existing')
        self.assertFailure(d, error.NodeNotFound)
        return d

    def testGetNodeIDs(self):
        def cb(node_ids):
            self.assertIn('pre-existing', node_ids)
            self.assertNotIn('non-existing', node_ids)

        return self.s.get_node_ids().addCallback(cb)

    def testCreateExistingNode(self):
        d = self.s.create_node('pre-existing', OWNER)
        self.assertFailure(d, error.NodeExists)
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
        self.assertFailure(d, error.NodeNotFound)
        return d

    def testDeleteNode(self):
        def cb(void):
            d = self.s.get_node('to-be-deleted')
            self.assertFailure(d, error.NodeNotFound)
            return d

        d = self.s.delete_node('to-be-deleted')
        d.addCallback(cb)
        return d

    def testGetAffiliations(self):
        def cb(affiliations):
            self.assertIn(('pre-existing', 'owner'), affiliations)

        d = self.s.get_affiliations(OWNER)
        d.addCallback(cb)
        return d

    def testGetSubscriptions(self):
        def cb(subscriptions):
            self.assertIn(('pre-existing', SUBSCRIBER, 'subscribed'), subscriptions)

        d = self.s.get_subscriptions(SUBSCRIBER)
        d.addCallback(cb)
        return d

    # Node tests

    def testGetType(self):
        self.assertEqual(self.node.get_type(), 'leaf')

    def testGetConfiguration(self):
        config = self.node.get_configuration()
        self.assertIn('pubsub#persist_items', config.iterkeys())
        self.assertIn('pubsub#deliver_payloads', config.iterkeys())
        self.assertEqual(config['pubsub#persist_items'], True)
        self.assertEqual(config['pubsub#deliver_payloads'], True)

    def testSetConfiguration(self):
        def get_config(node):
            d = node.set_configuration({'pubsub#persist_items': False})
            d.addCallback(lambda _: node)
            return d

        def check_object_config(node):
            config = node.get_configuration()
            self.assertEqual(config['pubsub#persist_items'], False)

        def get_node(void):
            return self.s.get_node('to-be-reconfigured')

        def check_storage_config(node):
            config = node.get_configuration()
            self.assertEqual(config['pubsub#persist_items'], False)

        d = self.s.get_node('to-be-reconfigured')
        d.addCallback(get_config)
        d.addCallback(check_object_config)
        d.addCallback(get_node)
        d.addCallback(check_storage_config)
        return d

    def testGetMetaData(self):
        meta_data = self.node.get_meta_data()
        for key, value in self.node.get_configuration().iteritems():
            self.assertIn(key, meta_data.iterkeys())
            self.assertEqual(value, meta_data[key])
        self.assertIn('pubsub#node_type', meta_data.iterkeys())
        self.assertEqual(meta_data['pubsub#node_type'], 'leaf')

    def testGetAffiliation(self):
        def cb(affiliation):
            self.assertEqual(affiliation, 'owner')

        d = self.node.get_affiliation(OWNER)
        d.addCallback(cb)
        return d

    def testGetNonExistingAffiliation(self):
        def cb(affiliation):
            self.assertEqual(affiliation, None)

        d = self.node.get_affiliation(SUBSCRIBER)
        d.addCallback(cb)
        return d

    def testAddSubscription(self):
        def cb1(void):
            return self.node.get_subscription(SUBSCRIBER_NEW)

        def cb2(state):
            self.assertEqual(state, 'pending')

        d = self.node.add_subscription(SUBSCRIBER_NEW, 'pending')
        d.addCallback(cb1)
        d.addCallback(cb2)
        return d

    def testAddExistingSubscription(self):
        d = self.node.add_subscription(SUBSCRIBER, 'pending')
        self.assertFailure(d, error.SubscriptionExists)
        return d

    def testGetSubscription(self):
        def cb(subscriptions):
            self.assertEquals(subscriptions[0][1], 'subscribed')
            self.assertEquals(subscriptions[1][1], 'pending')
            self.assertEquals(subscriptions[2][1], None)

        d = defer.DeferredList([self.node.get_subscription(SUBSCRIBER),
                                self.node.get_subscription(SUBSCRIBER_PENDING),
                                self.node.get_subscription(OWNER)])
        d.addCallback(cb)
        return d

    def testRemoveSubscription(self):
        return self.node.remove_subscription(SUBSCRIBER_TO_BE_DELETED)

    def testRemoveNonExistingSubscription(self):
        d = self.node.remove_subscription(OWNER)
        self.assertFailure(d, error.NotSubscribed)
        return d

    def testGetSubscribers(self):
        def cb(subscribers):
            self.assertIn(SUBSCRIBER, subscribers)
            self.assertNotIn(SUBSCRIBER_PENDING, subscribers)
            self.assertNotIn(OWNER, subscribers)

        d = self.node.get_subscribers()
        d.addCallback(cb)
        return d

    def testIsSubscriber(self):
        def cb(subscribed):
            self.assertEquals(subscribed[0][1], True)
            self.assertEquals(subscribed[1][1], True)
            self.assertEquals(subscribed[2][1], False)
            self.assertEquals(subscribed[3][1], False)

        d = defer.DeferredList([self.node.is_subscribed(SUBSCRIBER),
                                self.node.is_subscribed(SUBSCRIBER.userhostJID()),
                                self.node.is_subscribed(SUBSCRIBER_PENDING),
                                self.node.is_subscribed(OWNER)])
        d.addCallback(cb)
        return d

    def testStoreItems(self):
        def cb1(void):
            return self.node.get_items_by_id(['new'])

        def cb2(result):
            self.assertEqual(result[0], decode(ITEM_NEW.toXml()))

        d = self.node.store_items([ITEM_NEW], PUBLISHER)
        d.addCallback(cb1)
        d.addCallback(cb2)
        return d

    def testStoreUpdatedItems(self):
        def cb1(void):
            return self.node.get_items_by_id(['current'])

        def cb2(result):
            self.assertEqual(result[0], decode(ITEM_UPDATED.toXml()))

        d = self.node.store_items([ITEM_UPDATED], PUBLISHER)
        d.addCallback(cb1)
        d.addCallback(cb2)
        return d

    def testRemoveItems(self):
        def cb1(result):
            self.assertEqual(result, ['to-be-deleted'])
            return self.node.get_items_by_id(['to-be-deleted'])

        def cb2(result):
            self.assertEqual(len(result), 0)

        d = self.node.remove_items(['to-be-deleted'])
        d.addCallback(cb1)
        d.addCallback(cb2)
        return d

    def testRemoveNonExistingItems(self):
        def cb(result):
            self.assertEqual(result, [])

        d = self.node.remove_items(['non-existing'])
        d.addCallback(cb)
        return d

    def testGetItems(self):
        def cb(result):
            self.assertIn(decode(ITEM.toXml()), result)

        d = self.node.get_items()
        d.addCallback(cb)
        return d

    def testLastItem(self):
        def cb(result):
            self.assertEqual([decode(ITEM.toXml())], result)

        d = self.node.get_items(1)
        d.addCallback(cb)
        return d

    def testGetItemsById(self):
        def cb(result):
            self.assertEqual(len(result), 1)

        d = self.node.get_items_by_id(['current'])
        d.addCallback(cb)
        return d

    def testGetNonExistingItemsById(self):
        def cb(result):
            self.assertEqual(len(result), 0)

        d = self.node.get_items_by_id(['non-existing'])
        d.addCallback(cb)
        return d

    def testPurge(self):
        def cb1(node):
            d = node.purge()
            d.addCallback(lambda _: node)
            return d

        def cb2(node):
            return node.get_items()

        def cb3(result):
            self.assertEqual([], result)

        d = self.s.get_node('to-be-purged')
        d.addCallback(cb1)
        d.addCallback(cb2)
        d.addCallback(cb3)
        return d

    def testGetNodeAffilatiations(self):
        def cb1(node):
            return node.get_affiliations()

        def cb2(affiliations):
            affiliations = dict(((a[0].full(), a[1]) for a in affiliations))
            self.assertEquals(affiliations[OWNER.full()], 'owner')

        d = self.s.get_node('pre-existing')
        d.addCallback(cb1)
        d.addCallback(cb2)
        return d


class MemoryStorageStorageTestCase(unittest.TestCase, StorageTests):

    def setUp(self):
        from idavoll.memory_storage import Storage, LeafNode, Subscription, \
                                           default_config
        self.s = Storage()
        self.s._nodes['pre-existing'] = \
                LeafNode('pre-existing', OWNER, default_config)
        self.s._nodes['to-be-deleted'] = \
                LeafNode('to-be-deleted', OWNER, None)
        self.s._nodes['to-be-reconfigured'] = \
                LeafNode('to-be-reconfigured', OWNER, default_config)
        self.s._nodes['to-be-purged'] = \
                LeafNode('to-be-purged', OWNER, None)

        subscriptions = self.s._nodes['pre-existing']._subscriptions
        subscriptions[SUBSCRIBER.full()] = Subscription('subscribed')
        subscriptions[SUBSCRIBER_TO_BE_DELETED.full()] = \
                Subscription('subscribed')
        subscriptions[SUBSCRIBER_PENDING.full()] = \
                Subscription('pending')

        item = (decode(ITEM_TO_BE_DELETED.toXml()), PUBLISHER)
        self.s._nodes['pre-existing']._items['to-be-deleted'] = item
        self.s._nodes['pre-existing']._itemlist.append(item)
        self.s._nodes['to-be-purged']._items['to-be-deleted'] = item
        self.s._nodes['to-be-purged']._itemlist.append(item)
        item = (decode(ITEM.toXml()), PUBLISHER)
        self.s._nodes['pre-existing']._items['current'] = item
        self.s._nodes['pre-existing']._itemlist.append(item)

        return StorageTests.setUp(self)


class PgsqlStorageStorageTestCase(unittest.TestCase, StorageTests):
    def _callSuperSetUp(self, void):
        return StorageTests.setUp(self)

    def setUp(self):
        from idavoll.pgsql_storage import Storage
        self.s = Storage('ralphm', 'pubsub_test')
        self.s._dbpool.start()
        d = self.s._dbpool.runInteraction(self.init)
        d.addCallback(self._callSuperSetUp)
        return d

    def tearDownClass(self):
        #return self.s._dbpool.runInteraction(self.cleandb)
        pass

    def init(self, cursor):
        self.cleandb(cursor)
        cursor.execute("""INSERT INTO nodes (node) VALUES ('pre-existing')""")
        cursor.execute("""INSERT INTO nodes (node) VALUES ('to-be-deleted')""")
        cursor.execute("""INSERT INTO nodes (node) VALUES ('to-be-reconfigured')""")
        cursor.execute("""INSERT INTO nodes (node) VALUES ('to-be-purged')""")
        cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                       OWNER.userhost())
        cursor.execute("""INSERT INTO affiliations
                          (node_id, entity_id, affiliation)
                          SELECT nodes.id, entities.id, 'owner'
                          FROM nodes, entities
                          WHERE node='pre-existing' AND jid=%s""",
                       OWNER.userhost())
        cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                       SUBSCRIBER.userhost())
        cursor.execute("""INSERT INTO subscriptions
                          (node_id, entity_id, resource, subscription)
                          SELECT nodes.id, entities.id, %s, 'subscribed'
                          FROM nodes, entities
                          WHERE node='pre-existing' AND jid=%s""",
                       (SUBSCRIBER.resource,
                        SUBSCRIBER.userhost()))
        cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                       SUBSCRIBER_TO_BE_DELETED.userhost())
        cursor.execute("""INSERT INTO subscriptions
                          (node_id, entity_id, resource, subscription)
                          SELECT nodes.id, entities.id, %s, 'subscribed'
                          FROM nodes, entities
                          WHERE node='pre-existing' AND jid=%s""",
                       (SUBSCRIBER_TO_BE_DELETED.resource,
                        SUBSCRIBER_TO_BE_DELETED.userhost()))
        cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                       SUBSCRIBER_PENDING.userhost())
        cursor.execute("""INSERT INTO subscriptions
                          (node_id, entity_id, resource, subscription)
                          SELECT nodes.id, entities.id, %s, 'pending'
                          FROM nodes, entities
                          WHERE node='pre-existing' AND jid=%s""",
                       (SUBSCRIBER_PENDING.resource,
                        SUBSCRIBER_PENDING.userhost()))
        cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                       PUBLISHER.userhost())
        cursor.execute("""INSERT INTO items
                          (node_id, publisher, item, data, date)
                          SELECT nodes.id, %s, 'to-be-deleted', %s,
                                 now() - interval '1 day'
                          FROM nodes
                          WHERE node='pre-existing'""",
                       (PUBLISHER.userhost(),
                        ITEM_TO_BE_DELETED.toXml()))
        cursor.execute("""INSERT INTO items (node_id, publisher, item, data)
                          SELECT nodes.id, %s, 'to-be-deleted', %s
                          FROM nodes
                          WHERE node='to-be-purged'""",
                       (PUBLISHER.userhost(),
                        ITEM_TO_BE_DELETED.toXml()))
        cursor.execute("""INSERT INTO items (node_id, publisher, item, data)
                          SELECT nodes.id, %s, 'current', %s
                          FROM nodes
                          WHERE node='pre-existing'""",
                       (PUBLISHER.userhost(),
                        ITEM.toXml()))

    def cleandb(self, cursor):
        cursor.execute("""DELETE FROM nodes WHERE node in
                          ('non-existing', 'pre-existing', 'to-be-deleted',
                           'new 1', 'new 2', 'new 3', 'to-be-reconfigured',
                           'to-be-purged')""")
        cursor.execute("""DELETE FROM entities WHERE jid=%s""",
                       OWNER.userhost())
        cursor.execute("""DELETE FROM entities WHERE jid=%s""",
                       SUBSCRIBER.userhost())
        cursor.execute("""DELETE FROM entities WHERE jid=%s""",
                       SUBSCRIBER_TO_BE_DELETED.userhost())
        cursor.execute("""DELETE FROM entities WHERE jid=%s""",
                       SUBSCRIBER_PENDING.userhost())
        cursor.execute("""DELETE FROM entities WHERE jid=%s""",
                       PUBLISHER.userhost())

try:
    import pyPgSQL
    pyPgSQL
except ImportError:
    PgsqlStorageStorageTestCase.skip = "pyPgSQL not available"

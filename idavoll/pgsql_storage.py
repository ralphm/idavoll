# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

import copy

from zope.interface import implements
from twisted.words.protocols.jabber import jid
from wokkel.generic import parseXml

from idavoll import error, iidavoll

class Storage:

    implements(iidavoll.IStorage)


    def __init__(self, dbpool):
        self.dbpool = dbpool


    def getNode(self, nodeIdentifier):
        return self.dbpool.runInteraction(self._getNode, nodeIdentifier)


    def _getNode(self, cursor, nodeIdentifier):
        configuration = {}
        cursor.execute("""SELECT persistent, deliver_payload,
                                 send_last_published_item
                          FROM nodes
                          WHERE node=%s""",
                       (nodeIdentifier,))
        try:
            (configuration["pubsub#persist_items"],
             configuration["pubsub#deliver_payloads"],
             configuration["pubsub#send_last_published_item"]) = \
            cursor.fetchone()
        except TypeError:
            raise error.NodeNotFound()
        else:
            node = LeafNode(nodeIdentifier, configuration)
            node.dbpool = self.dbpool
            return node


    def getNodeIds(self):
        d = self.dbpool.runQuery("""SELECT node from nodes""")
        d.addCallback(lambda results: [r[0] for r in results])
        return d


    def createNode(self, nodeIdentifier, owner, config=None):
        return self.dbpool.runInteraction(self._createNode, nodeIdentifier,
                                           owner)


    def _createNode(self, cursor, nodeIdentifier, owner):
        owner = owner.userhost()
        try:
            cursor.execute("""INSERT INTO nodes (node) VALUES (%s)""",
                           (nodeIdentifier))
        except cursor._pool.dbapi.OperationalError:
            raise error.NodeExists()

        cursor.execute("""SELECT 1 from entities where jid=%s""",
                       (owner))

        if not cursor.fetchone():
            cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                           (owner))

        cursor.execute("""INSERT INTO affiliations
                          (node_id, entity_id, affiliation)
                          SELECT n.id, e.id, 'owner' FROM
                          (SELECT id FROM nodes WHERE node=%s) AS n
                          CROSS JOIN
                          (SELECT id FROM entities WHERE jid=%s) AS e""",
                       (nodeIdentifier, owner))


    def deleteNode(self, nodeIdentifier):
        return self.dbpool.runInteraction(self._deleteNode, nodeIdentifier)


    def _deleteNode(self, cursor, nodeIdentifier):
        cursor.execute("""DELETE FROM nodes WHERE node=%s""",
                       (nodeIdentifier,))

        if cursor.rowcount != 1:
            raise error.NodeNotFound()


    def getAffiliations(self, entity):
        d = self.dbpool.runQuery("""SELECT node, affiliation FROM entities
                                        JOIN affiliations ON
                                        (affiliations.entity_id=entities.id)
                                        JOIN nodes ON
                                        (nodes.id=affiliations.node_id)
                                        WHERE jid=%s""",
                                     (entity.userhost(),))
        d.addCallback(lambda results: [tuple(r) for r in results])
        return d


    def getSubscriptions(self, entity):
        d = self.dbpool.runQuery("""SELECT node, jid, resource, subscription
                                     FROM entities JOIN subscriptions ON
                                     (subscriptions.entity_id=entities.id)
                                     JOIN nodes ON
                                     (nodes.id=subscriptions.node_id)
                                     WHERE jid=%s""",
                                  (entity.userhost(),))
        d.addCallback(self._convertSubscriptionJIDs)
        return d


    def _convertSubscriptionJIDs(self, subscriptions):
        return [(node,
                 jid.internJID('%s/%s' % (subscriber, resource)),
                 subscription)
                for node, subscriber, resource, subscription in subscriptions]



class Node:

    implements(iidavoll.INode)

    def __init__(self, nodeIdentifier, config):
        self.nodeIdentifier = nodeIdentifier
        self._config = config


    def _checkNodeExists(self, cursor):
        cursor.execute("""SELECT id FROM nodes WHERE node=%s""",
                       (self.nodeIdentifier))
        if not cursor.fetchone():
            raise error.NodeNotFound()


    def getType(self):
        return self.nodeType


    def getConfiguration(self):
        return self._config


    def setConfiguration(self, options):
        config = copy.copy(self._config)

        for option in options:
            if option in config:
                config[option] = options[option]

        d = self.dbpool.runInteraction(self._setConfiguration, config)
        d.addCallback(self._setCachedConfiguration, config)
        return d


    def _setConfiguration(self, cursor, config):
        self._checkNodeExists(cursor)
        cursor.execute("""UPDATE nodes SET persistent=%s, deliver_payload=%s,
                                           send_last_published_item=%s
                          WHERE node=%s""",
                       (config["pubsub#persist_items"],
                        config["pubsub#deliver_payloads"],
                        config["pubsub#send_last_published_item"],
                        self.nodeIdentifier))


    def _setCachedConfiguration(self, void, config):
        self._config = config


    def getMetaData(self):
        config = copy.copy(self._config)
        config["pubsub#node_type"] = self.nodeType
        return config


    def getAffiliation(self, entity):
        return self.dbpool.runInteraction(self._getAffiliation, entity)


    def _getAffiliation(self, cursor, entity):
        self._checkNodeExists(cursor)
        cursor.execute("""SELECT affiliation FROM affiliations
                          JOIN nodes ON (node_id=nodes.id)
                          JOIN entities ON (entity_id=entities.id)
                          WHERE node=%s AND jid=%s""",
                       (self.nodeIdentifier,
                        entity.userhost()))

        try:
            return cursor.fetchone()[0]
        except TypeError:
            return None


    def getSubscription(self, subscriber):
        return self.dbpool.runInteraction(self._getSubscription, subscriber)


    def _getSubscription(self, cursor, subscriber):
        self._checkNodeExists(cursor)

        userhost = subscriber.userhost()
        resource = subscriber.resource or ''

        cursor.execute("""SELECT subscription FROM subscriptions
                          JOIN nodes ON (nodes.id=subscriptions.node_id)
                          JOIN entities ON
                               (entities.id=subscriptions.entity_id)
                          WHERE node=%s AND jid=%s AND resource=%s""",
                       (self.nodeIdentifier,
                        userhost,
                        resource))
        try:
            return cursor.fetchone()[0]
        except TypeError:
            return None


    def addSubscription(self, subscriber, state):
        return self.dbpool.runInteraction(self._addSubscription, subscriber,
                                          state)


    def _addSubscription(self, cursor, subscriber, state):
        self._checkNodeExists(cursor)

        userhost = subscriber.userhost()
        resource = subscriber.resource or ''

        try:
            cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                           (userhost))
        except cursor._pool.dbapi.OperationalError:
            pass

        try:
            cursor.execute("""INSERT INTO subscriptions
                              (node_id, entity_id, resource, subscription)
                              SELECT n.id, e.id, %s, %s FROM
                              (SELECT id FROM nodes WHERE node=%s) AS n
                              CROSS JOIN
                              (SELECT id FROM entities WHERE jid=%s) AS e""",
                           (resource,
                            state,
                            self.nodeIdentifier,
                            userhost))
        except cursor._pool.dbapi.OperationalError:
            raise error.SubscriptionExists()


    def removeSubscription(self, subscriber):
        return self.dbpool.runInteraction(self._removeSubscription,
                                           subscriber)


    def _removeSubscription(self, cursor, subscriber):
        self._checkNodeExists(cursor)

        userhost = subscriber.userhost()
        resource = subscriber.resource or ''

        cursor.execute("""DELETE FROM subscriptions WHERE
                          node_id=(SELECT id FROM nodes WHERE node=%s) AND
                          entity_id=(SELECT id FROM entities WHERE jid=%s)
                          AND resource=%s""",
                       (self.nodeIdentifier,
                        userhost,
                        resource))
        if cursor.rowcount != 1:
            raise error.NotSubscribed()

        return None


    def getSubscribers(self):
        d = self.dbpool.runInteraction(self._getSubscribers)
        d.addCallback(self._convertToJIDs)
        return d


    def _getSubscribers(self, cursor):
        self._checkNodeExists(cursor)
        cursor.execute("""SELECT jid, resource FROM subscriptions
                          JOIN nodes ON (node_id=nodes.id)
                          JOIN entities ON (entity_id=entities.id)
                          WHERE node=%s AND
                          subscription='subscribed'""",
                       (self.nodeIdentifier,))
        return cursor.fetchall()


    def _convertToJIDs(self, list):
        return [jid.internJID("%s/%s" % (l[0], l[1])) for l in list]


    def isSubscribed(self, entity):
        return self.dbpool.runInteraction(self._isSubscribed, entity)


    def _isSubscribed(self, cursor, entity):
        self._checkNodeExists(cursor)

        cursor.execute("""SELECT 1 FROM entities
                          JOIN subscriptions ON
                          (entities.id=subscriptions.entity_id)
                          JOIN nodes ON
                          (nodes.id=subscriptions.node_id)
                          WHERE entities.jid=%s
                          AND node=%s AND subscription='subscribed'""",
                       (entity.userhost(),
                       self.nodeIdentifier))

        return cursor.fetchone() is not None


    def getAffiliations(self):
        return self.dbpool.runInteraction(self._getAffiliations)


    def _getAffiliations(self, cursor):
        self._checkNodeExists(cursor)

        cursor.execute("""SELECT jid, affiliation FROM nodes
                          JOIN affiliations ON
                            (nodes.id = affiliations.node_id)
                          JOIN entities ON
                            (affiliations.entity_id = entities.id)
                          WHERE node=%s""",
                       self.nodeIdentifier)
        result = cursor.fetchall()

        return [(jid.internJID(r[0]), r[1]) for r in result]



class LeafNodeMixin:

    nodeType = 'leaf'

    def storeItems(self, items, publisher):
        return self.dbpool.runInteraction(self._storeItems, items, publisher)


    def _storeItems(self, cursor, items, publisher):
        self._checkNodeExists(cursor)
        for item in items:
            self._storeItem(cursor, item, publisher)


    def _storeItem(self, cursor, item, publisher):
        data = item.toXml()
        cursor.execute("""UPDATE items SET date=now(), publisher=%s, data=%s
                          FROM nodes
                          WHERE nodes.id = items.node_id AND
                                nodes.node = %s and items.item=%s""",
                       (publisher.full(),
                        data,
                        self.nodeIdentifier,
                        item["id"]))
        if cursor.rowcount == 1:
            return

        cursor.execute("""INSERT INTO items (node_id, item, publisher, data)
                          SELECT id, %s, %s, %s FROM nodes WHERE node=%s""",
                       (item["id"],
                        publisher.full(),
                        data,
                        self.nodeIdentifier))


    def removeItems(self, itemIdentifiers):
        return self.dbpool.runInteraction(self._removeItems, itemIdentifiers)


    def _removeItems(self, cursor, itemIdentifiers):
        self._checkNodeExists(cursor)

        deleted = []

        for itemIdentifier in itemIdentifiers:
            cursor.execute("""DELETE FROM items WHERE
                              node_id=(SELECT id FROM nodes WHERE node=%s) AND
                              item=%s""",
                           (self.nodeIdentifier,
                            itemIdentifier))

            if cursor.rowcount:
                deleted.append(itemIdentifier)

        return deleted


    def getItems(self, maxItems=None):
        return self.dbpool.runInteraction(self._getItems, maxItems)


    def _getItems(self, cursor, maxItems):
        self._checkNodeExists(cursor)
        query = """SELECT data FROM nodes JOIN items ON
                   (nodes.id=items.node_id)
                   WHERE node=%s ORDER BY date DESC"""
        if maxItems:
            cursor.execute(query + " LIMIT %s",
                           (self.nodeIdentifier,
                            maxItems))
        else:
            cursor.execute(query, (self.nodeIdentifier))

        result = cursor.fetchall()
        return [parseXml(r[0]) for r in result]


    def getItemsById(self, itemIdentifiers):
        return self.dbpool.runInteraction(self._getItemsById, itemIdentifiers)


    def _getItemsById(self, cursor, itemIdentifiers):
        self._checkNodeExists(cursor)
        items = []
        for itemIdentifier in itemIdentifiers:
            cursor.execute("""SELECT data FROM nodes JOIN items ON
                              (nodes.id=items.node_id)
                              WHERE node=%s AND item=%s""",
                           (self.nodeIdentifier,
                            itemIdentifier))
            result = cursor.fetchone()
            if result:
                items.append(parseXml(result[0]))
        return items


    def purge(self):
        return self.dbpool.runInteraction(self._purge)


    def _purge(self, cursor):
        self._checkNodeExists(cursor)

        cursor.execute("""DELETE FROM items WHERE
                          node_id=(SELECT id FROM nodes WHERE node=%s)""",
                       (self.nodeIdentifier,))



class LeafNode(Node, LeafNodeMixin):

    implements(iidavoll.ILeafNode)



class GatewayStorage(object):
    """
    Memory based storage facility for the XMPP-HTTP gateway.
    """

    def __init__(self, dbpool):
        self.dbpool = dbpool


    def _countCallbacks(self, cursor, service, nodeIdentifier):
        """
        Count number of callbacks registered for a node.
        """
        cursor.execute("""SELECT count(*) FROM callbacks
                          WHERE service=%s and node=%s""",
                       service.full(),
                       nodeIdentifier)
        results = cursor.fetchall()
        return results[0][0]


    def addCallback(self, service, nodeIdentifier, callback):
        def interaction(cursor):
            cursor.execute("""SELECT 1 FROM callbacks
                              WHERE service=%s and node=%s and uri=%s""",
                           service.full(),
                           nodeIdentifier,
                           callback)
            if cursor.fetchall():
                raise error.SubscriptionExists()

            cursor.execute("""INSERT INTO callbacks
                              (service, node, uri) VALUES
                              (%s, %s, %s)""",
                           service.full(),
                           nodeIdentifier,
                           callback)

        return self.dbpool.runInteraction(interaction)


    def removeCallback(self, service, nodeIdentifier, callback):
        def interaction(cursor):
            cursor.execute("""DELETE FROM callbacks
                              WHERE service=%s and node=%s and uri=%s""",
                           service.full(),
                           nodeIdentifier,
                           callback)

            if cursor.rowcount != 1:
                raise error.NotSubscribed()

            last = not self._countCallbacks(cursor, service, nodeIdentifier)
            return last

        return self.dbpool.runInteraction(interaction)

    def getCallbacks(self, service, nodeIdentifier):
        def interaction(cursor):
            cursor.execute("""SELECT uri FROM callbacks
                              WHERE service=%s and node=%s""",
                           service.full(),
                           nodeIdentifier)
            results = cursor.fetchall()

            if not results:
                raise error.NoCallbacks()

            return [result[0] for result in results]

        return self.dbpool.runInteraction(interaction)


    def hasCallbacks(self, service, nodeIdentifier):
        def interaction(cursor):
            return bool(self._countCallbacks(cursor, service, nodeIdentifier))

        return self.dbpool.runInteraction(interaction)

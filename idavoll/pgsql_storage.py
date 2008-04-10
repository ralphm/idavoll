# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

import copy
from twisted.enterprise import adbapi
from twisted.words.protocols.jabber import jid
from zope.interface import implements

from idavoll import error, iidavoll

class Storage:

    implements(iidavoll.IStorage)

    def __init__(self, user, database, password=None, host=None, port=None):
        self._dbpool = adbapi.ConnectionPool('pyPgSQL.PgSQL',
                                             user=user,
                                             password=password,
                                             database=database,
                                             host=host,
                                             port=port,
                                             cp_reconnect=True,
                                             client_encoding='utf-8'
                                             )

    def get_node(self, node_id):
        return self._dbpool.runInteraction(self._get_node, node_id)

    def _get_node(self, cursor, node_id):
        configuration = {}
        cursor.execute("""SELECT persistent, deliver_payload,
                                 send_last_published_item
                          FROM nodes
                          WHERE node=%s""",
                       (node_id,))
        try:
            (configuration["pubsub#persist_items"],
             configuration["pubsub#deliver_payloads"],
             configuration["pubsub#send_last_published_item"]) = \
            cursor.fetchone()
        except TypeError:
            raise error.NodeNotFound()
        else:
            node = LeafNode(node_id, configuration)
            node._dbpool = self._dbpool
            return node

    def get_node_ids(self):
        d = self._dbpool.runQuery("""SELECT node from nodes""")
        d.addCallback(lambda results: [r[0] for r in results])
        return d

    def create_node(self, node_id, owner, config=None):
        return self._dbpool.runInteraction(self._create_node, node_id, owner)

    def _create_node(self, cursor, node_id, owner):
        node_id = node_id
        owner = owner.userhost()
        try:
            cursor.execute("""INSERT INTO nodes (node) VALUES (%s)""",
                           (node_id))
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
                       (node_id, owner))

    def delete_node(self, node_id):
        return self._dbpool.runInteraction(self._delete_node, node_id)

    def _delete_node(self, cursor, node_id):
        cursor.execute("""DELETE FROM nodes WHERE node=%s""",
                       (node_id,))

        if cursor.rowcount != 1:
            raise error.NodeNotFound()

    def get_affiliations(self, entity):
        d = self._dbpool.runQuery("""SELECT node, affiliation FROM entities
                                        JOIN affiliations ON
                                        (affiliations.entity_id=entities.id)
                                        JOIN nodes ON
                                        (nodes.id=affiliations.node_id)
                                        WHERE jid=%s""",
                                     (entity.userhost(),))
        d.addCallback(lambda results: [tuple(r) for r in results])
        return d

    def get_subscriptions(self, entity):
        d = self._dbpool.runQuery("""SELECT node, jid, resource, subscription
                                     FROM entities JOIN subscriptions ON
                                     (subscriptions.entity_id=entities.id)
                                     JOIN nodes ON
                                     (nodes.id=subscriptions.node_id)
                                     WHERE jid=%s""",
                                  (entity.userhost(),))
        d.addCallback(self._convert_subscription_jids)
        return d

    def _convert_subscription_jids(self, subscriptions):
        return [(node,
                 jid.internJID('%s/%s' % (subscriber, resource)),
                 subscription)
                for node, subscriber, resource, subscription in subscriptions]


class Node:

    implements(iidavoll.INode)

    def __init__(self, node_id, config):
        self.id = node_id
        self._config = config

    def _check_node_exists(self, cursor):
        cursor.execute("""SELECT id FROM nodes WHERE node=%s""",
                       (self.id))
        if not cursor.fetchone():
            raise error.NodeNotFound()

    def get_type(self):
        return self.type

    def get_configuration(self):
        return self._config

    def set_configuration(self, options):
        config = copy.copy(self._config)

        for option in options:
            if option in config:
                config[option] = options[option]

        d = self._dbpool.runInteraction(self._set_configuration, config)
        d.addCallback(self._set_cached_configuration, config)
        return d

    def _set_configuration(self, cursor, config):
        self._check_node_exists(cursor)
        cursor.execute("""UPDATE nodes SET persistent=%s, deliver_payload=%s,
                                           send_last_published_item=%s
                          WHERE node=%s""",
                       (config["pubsub#persist_items"],
                        config["pubsub#deliver_payloads"],
                        config["pubsub#send_last_published_item"],
                        self.id))

    def _set_cached_configuration(self, void, config):
        self._config = config

    def get_meta_data(self):
        config = copy.copy(self._config)
        config["pubsub#node_type"] = self.type
        return config

    def get_affiliation(self, entity):
        return self._dbpool.runInteraction(self._get_affiliation, entity)

    def _get_affiliation(self, cursor, entity):
        self._check_node_exists(cursor)
        cursor.execute("""SELECT affiliation FROM affiliations
                          JOIN nodes ON (node_id=nodes.id)
                          JOIN entities ON (entity_id=entities.id)
                          WHERE node=%s AND jid=%s""",
                       (self.id,
                        entity.userhost()))

        try:
            return cursor.fetchone()[0]
        except TypeError:
            return None

    def get_subscription(self, subscriber):
        return self._dbpool.runInteraction(self._get_subscription, subscriber)

    def _get_subscription(self, cursor, subscriber):
        self._check_node_exists(cursor)

        userhost = subscriber.userhost()
        resource = subscriber.resource or ''

        cursor.execute("""SELECT subscription FROM subscriptions
                          JOIN nodes ON (nodes.id=subscriptions.node_id)
                          JOIN entities ON
                               (entities.id=subscriptions.entity_id)
                          WHERE node=%s AND jid=%s AND resource=%s""",
                       (self.id,
                        userhost,
                        resource))
        try:
            return cursor.fetchone()[0]
        except TypeError:
            return None

    def add_subscription(self, subscriber, state):
        return self._dbpool.runInteraction(self._add_subscription, subscriber,
                                          state)

    def _add_subscription(self, cursor, subscriber, state):
        self._check_node_exists(cursor)

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
                            self.id,
                            userhost))
        except cursor._pool.dbapi.OperationalError:
            raise error.SubscriptionExists()

    def remove_subscription(self, subscriber):
        return self._dbpool.runInteraction(self._remove_subscription,
                                           subscriber)

    def _remove_subscription(self, cursor, subscriber):
        self._check_node_exists(cursor)

        userhost = subscriber.userhost()
        resource = subscriber.resource or ''

        cursor.execute("""DELETE FROM subscriptions WHERE
                          node_id=(SELECT id FROM nodes WHERE node=%s) AND
                          entity_id=(SELECT id FROM entities WHERE jid=%s)
                          AND resource=%s""",
                       (self.id,
                        userhost,
                        resource))
        if cursor.rowcount != 1:
            raise error.NotSubscribed()

        return None

    def get_subscribers(self):
        d = self._dbpool.runInteraction(self._get_subscribers)
        d.addCallback(self._convert_to_jids)
        return d

    def _get_subscribers(self, cursor):
        self._check_node_exists(cursor)
        cursor.execute("""SELECT jid, resource FROM subscriptions
                          JOIN nodes ON (node_id=nodes.id)
                          JOIN entities ON (entity_id=entities.id)
                          WHERE node=%s AND
                          subscription='subscribed'""",
                       (self.id,))
        return cursor.fetchall()

    def _convert_to_jids(self, list):
        return [jid.internJID("%s/%s" % (l[0], l[1])) for l in list]

    def is_subscribed(self, entity):
        return self._dbpool.runInteraction(self._is_subscribed, entity)

    def _is_subscribed(self, cursor, entity):
        self._check_node_exists(cursor)

        cursor.execute("""SELECT 1 FROM entities
                          JOIN subscriptions ON
                          (entities.id=subscriptions.entity_id)
                          JOIN nodes ON
                          (nodes.id=subscriptions.node_id)
                          WHERE entities.jid=%s
                          AND node=%s AND subscription='subscribed'""",
                       (entity.userhost(),
                       self.id))

        return cursor.fetchone() is not None

    def get_affiliations(self):
        return self._dbpool.runInteraction(self._get_affiliations)

    def _get_affiliations(self, cursor):
        self._check_node_exists(cursor)

        cursor.execute("""SELECT jid, affiliation FROM nodes
                          JOIN affiliations ON
                            (nodes.id = affiliations.node_id)
                          JOIN entities ON
                            (affiliations.entity_id = entities.id)
                          WHERE node=%s""",
                       self.id)
        result = cursor.fetchall()

        return [(jid.internJID(r[0]), r[1]) for r in result]

class LeafNodeMixin:

    type = 'leaf'

    def store_items(self, items, publisher):
        return self._dbpool.runInteraction(self._store_items, items, publisher)

    def _store_items(self, cursor, items, publisher):
        self._check_node_exists(cursor)
        for item in items:
            self._store_item(cursor, item, publisher)

    def _store_item(self, cursor, item, publisher):
        data = item.toXml()
        cursor.execute("""UPDATE items SET date=now(), publisher=%s, data=%s
                          FROM nodes
                          WHERE nodes.id = items.node_id AND
                                nodes.node = %s and items.item=%s""",
                       (publisher.full(),
                        data,
                        self.id,
                        item["id"]))
        if cursor.rowcount == 1:
            return

        cursor.execute("""INSERT INTO items (node_id, item, publisher, data)
                          SELECT id, %s, %s, %s FROM nodes WHERE node=%s""",
                       (item["id"],
                        publisher.full(),
                        data,
                        self.id))

    def remove_items(self, item_ids):
        return self._dbpool.runInteraction(self._remove_items, item_ids)

    def _remove_items(self, cursor, item_ids):
        self._check_node_exists(cursor)

        deleted = []

        for item_id in item_ids:
            cursor.execute("""DELETE FROM items WHERE
                              node_id=(SELECT id FROM nodes WHERE node=%s) AND
                              item=%s""",
                           (self.id,
                            item_id))

            if cursor.rowcount:
                deleted.append(item_id)

        return deleted

    def get_items(self, max_items=None):
        return self._dbpool.runInteraction(self._get_items, max_items)

    def _get_items(self, cursor, max_items):
        self._check_node_exists(cursor)
        query = """SELECT data FROM nodes JOIN items ON
                   (nodes.id=items.node_id)
                   WHERE node=%s ORDER BY date DESC"""
        if max_items:
            cursor.execute(query + " LIMIT %s",
                           (self.id,
                            max_items))
        else:
            cursor.execute(query, (self.id))

        result = cursor.fetchall()
        return [unicode(r[0], 'utf-8') for r in result]

    def get_items_by_id(self, item_ids):
        return self._dbpool.runInteraction(self._get_items_by_id, item_ids)

    def _get_items_by_id(self, cursor, item_ids):
        self._check_node_exists(cursor)
        items = []
        for item_id in item_ids:
            cursor.execute("""SELECT data FROM nodes JOIN items ON
                              (nodes.id=items.node_id)
                              WHERE node=%s AND item=%s""",
                           (self.id,
                            item_id))
            result = cursor.fetchone()
            if result:
                items.append(unicode(result[0], 'utf-8'))
        return items

    def purge(self):
        return self._dbpool.runInteraction(self._purge)

    def _purge(self, cursor):
        self._check_node_exists(cursor)

        cursor.execute("""DELETE FROM items WHERE
                          node_id=(SELECT id FROM nodes WHERE node=%s)""",
                       (self.id,))

class LeafNode(Node, LeafNodeMixin):

    implements(iidavoll.ILeafNode)

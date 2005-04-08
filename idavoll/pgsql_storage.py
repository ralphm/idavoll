import copy
import storage
from twisted.enterprise import adbapi
from twisted.internet import defer
from twisted.words.protocols.jabber import jid
from zope.interface import implements

class Storage:

    implements(storage.IStorage)

    def __init__(self, user, database):
        self._dbpool = adbapi.ConnectionPool('pyPgSQL.PgSQL', user=user,
                database=database)

    def get_node(self, node_id):
        return self._dbpool.runInteraction(self._get_node, node_id)

    def _get_node(self, cursor, node_id):
        configuration = {}
        cursor.execute("""SELECT persistent, deliver_payload FROM nodes
                          WHERE node=%s""",
                       (node_id,))
        try:
            (configuration["pubsub#persist_items"],
             configuration["pubsub#deliver_payloads"]) = cursor.fetchone()
        except TypeError:
            raise storage.NodeNotFound
        else:
            node = LeafNode(node_id, configuration)
            node._dbpool = self._dbpool
            return node

    def get_node_ids(self):
        d = self._dbpool.runQuery("""SELECT node from nodes""")
        d.addCallback(lambda results: [r[0] for r in results])
        return d

    def create_node(self, node_id, owner, type='leaf'):
        return self._dbpool.runInteraction(self._create_node, node_id, owner)

    def _create_node(self, cursor, node_id, owner):
        try:
            cursor.execute("""INSERT INTO nodes (node) VALUES (%s)""",
                           (node_id.encode('utf8')))
        except:
            raise storage.NodeExists
       
        cursor.execute("""SELECT 1 from entities where jid=%s""",
                       (owner.full().encode('utf8')))

        if not cursor.fetchone():
            cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                           (owner.full().encode('utf8')))

        cursor.execute("""INSERT INTO affiliations
                          (node_id, entity_id, affiliation)
                          SELECT n.id, e.id, 'owner' FROM
                          (SELECT id FROM nodes WHERE node=%s) AS n
                          CROSS JOIN
                          (SELECT id FROM entities WHERE jid=%s) AS e""",
                       (node_id.encode('utf8'),
                        owner.full().encode('utf8')))

    def delete_node(self, node_id):
        return self._dbpool.runInteraction(self._delete_node, node_id)

    def _delete_node(self, cursor, node_id):
        cursor.execute("""DELETE FROM nodes WHERE node=%s""",
                       (node_id.encode('utf-8'),))

        if cursor.rowcount != 1:
            raise storage.NodeNotFound

    def get_affiliations(self, entity):
        d = self._dbpool.runQuery("""SELECT node, affiliation FROM entities
                                        JOIN affiliations ON
                                        (affiliations.entity_id=entities.id)
                                        JOIN nodes ON
                                        (nodes.id=affiliations.node_id)
                                        WHERE jid=%s""",
                                     (entity.full().encode('utf8'),))
        d.addCallback(lambda results: [tuple(r) for r in results])
        return d

    def get_subscriptions(self, entity):
        d = self._dbpool.runQuery("""SELECT node, jid, resource, subscription
                                     FROM entities JOIN subscriptions ON
                                     (subscriptions.entity_id=entities.id)
                                     JOIN nodes ON
                                     (nodes.id=subscriptions.node_id)
                                     WHERE jid=%s""",
                                  (entity.userhost().encode('utf8'),))
        d.addCallback(self._convert_subscription_jids)
        return d

    def _convert_subscription_jids(self, subscriptions):
        return [(node, jid.JID('%s/%s' % (subscriber, resource)), subscription)
                for node, subscriber, resource, subscription in subscriptions]

class Node:

    implements(storage.INode)

    def __init__(self, node_id, config):
        self.id = node_id
        self._config = config

    def get_type(self):
        return self.type

    def get_configuration(self):
        return self._config

    def set_configuration(self, options):
        return self._dbpool.runInteraction(self._set_node_configuration,
                                           options)

    def _set_configuration(self, cursor, options):
        for option in options:
            if option in self._config:
                self._config[option] = options[option]
        
        cursor.execute("""UPDATE nodes SET persistent=%s, deliver_payload=%s
                          WHERE node=%s""",
                       (self._config["pubsub#persist_items"].encode('utf8'),
                        self._config["pubsub#deliver_payloads"].encode('utf8'),
                        self.id.encode('utf-8')))

    def get_meta_data(self):
        config = copy.copy(self._config)
        config["pubsub#node_type"] = self.type
        return config

    def get_affiliation(self, entity):
        return self._dbpool.runInteraction(self._get_affiliation, entity)

    def _get_affiliation(self, cursor, entity):
        cursor.execute("""SELECT affiliation FROM affiliations
                          JOIN nodes ON (node_id=nodes.id)
                          JOIN entities ON (entity_id=entities.id)
                          WHERE node=%s AND jid=%s""",
                       (self.id.encode('utf8'),
                        entity.full().encode('utf8')))

        try:
            return cursor.fetchone()[0]
        except TypeError:
            return None

    def add_subscription(self, subscriber, state):
        return self._dbpool.runInteraction(self._add_subscription, subscriber,
                                          state)

    def _add_subscription(self, cursor, subscriber, state):
        userhost = subscriber.userhost()
        resource = subscriber.resource or ''

        try:
            cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                           (userhost.encode('utf8')))
        except:
            pass

        try:
            cursor.execute("""INSERT INTO subscriptions
                              (node_id, entity_id, resource, subscription)
                              SELECT n.id, e.id, %s, %s FROM
                              (SELECT id FROM nodes WHERE node=%s) AS n
                              CROSS JOIN
                              (SELECT id FROM entities WHERE jid=%s) AS e""",
                           (resource.encode('utf8'),
                            state.encode('utf8'),
                            self.id.encode('utf8'),
                            userhost.encode('utf8')))
        except:
            cursor.execute("""SELECT subscription FROM subscriptions
                              JOIN nodes ON (nodes.id=subscriptions.node_id)
                              JOIN entities ON
                                   (entities.id=subscriptions.entity_id)
                              WHERE node=%s AND jid=%s AND resource=%s""",
                           (self.id.encode('utf8'),
                            userhost.encode('utf8'),
                            resource.encode('utf8')))
            state = cursor.fetchone()[0]

        return {'node': self.id,
                'jid': subscriber,
                'subscription': state}

    def remove_subscription(self, subscriber, state):
        pass

    def get_subscribers(self):
        d = self._dbpool.runQuery("""SELECT jid, resource FROM subscriptions
                                     JOIN nodes ON (node_id=nodes.id)
                                     JOIN entities ON (entity_id=entities.id)
                                     WHERE node=%s AND
                                     subscription='subscribed'""",
                                  (self.id.encode('utf8'),))
        d.addCallback(self._convert_to_jids)
        return d

    def _convert_to_jids(self, list):
        return [jid.JID("%s/%s" % (l[0], l[1])) for l in list]

    def is_subscribed(self, subscriber):
        pass

class LeafNode(Node):

    implements(storage.ILeafNode)

    type = 'leaf'

    def store_items(self, items, publisher):
        return defer.succeed(None)

    def remove_items(self, item_ids):
        pass

    def get_items(self, max_items=None):
        pass

    def get_items_by_id(self, item_ids):
        pass

    def purge(self):
        pass

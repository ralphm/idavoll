from twisted.application import service
from twisted.internet import defer
from twisted.protocols.jabber import jid
from twisted.enterprise import adbapi
import backend

class Storage:
    def __init__(self, user, database):
        self.dbpool = adbapi.ConnectionPool('pyPgSQL.PgSQL', user=user,
                database=database)

    def _check_node_exists(self, cursor, node_id):
        cursor.execute("""SELECT id FROM nodes WHERE node=%s""",
                       (node_id.encode('utf8')))
        if not cursor.fetchone():
            raise backend.NodeNotFound
        else:
            return

    def _get_node_configuration(self, cursor, node_id):
        configuration = {}
        cursor.execute("""SELECT persistent, deliver_payload FROM nodes
                          WHERE node=%s""",
                       (node_id,))
        try:
            (configuration["persist_items"],
             configuration["deliver_payloads"]) = cursor.fetchone()
            return configuration
        except TypeError:
            raise backend.NodeNotFound

    def get_node_configuration(self, node_id):
        return self.dbpool.runInteraction(self._get_node_configuration, node_id)

    def _get_affiliation(self, cursor, node_id, entity):
        self._check_node_exists(cursor, node_id)
        cursor.execute("""SELECT affiliation FROM affiliations
                          JOIN nodes ON (node_id=nodes.id)
                          JOIN entities ON (entity_id=entities.id)
                          WHERE node=%s AND jid=%s""",
                       (node_id.encode('utf8'),
                        entity.full().encode('utf8')))

        try:
            return cursor.fetchone()[0]
        except TypeError:
            return None

    def get_affiliation(self, node_id, entity):
        return self.dbpool.runInteraction(self._get_affiliation, node_id,
                                          entity)

    def get_subscribers(self, node_id):
        d = self.dbpool.runInteraction(self._get_subscribers, node_id)
        d.addCallback(self._convert_to_jids)
        return d

    def _get_subscribers(self, cursor,node_id):
        self._check_node_exists(cursor, node_id)
        cursor.execute("""SELECT jid, resource FROM subscriptions
                          JOIN nodes ON (node_id=nodes.id)
                          JOIN entities ON (entity_id=entities.id)
                          WHERE node=%s AND
                          subscription='subscribed'""",
                       (node_id.encode('utf8'),))
        return cursor.fetchall()

    def _convert_to_jids(self, list):
        return [jid.JID("%s/%s" % (l[0], l[1])).full() for l in list]

    def store_items(self, node_id, items, publisher):
        return self.dbpool.runInteraction(self._store_items, node_id, items,
                                          publisher)

    def _store_items(self, cursor, node_id, items, publisher):
        self._check_node_exists(cursor, node_id)
        for item in items:
            self._store_item(cursor, node_id, item, publisher)

    def _store_item(self, cursor, node_id, item, publisher):
        data = item.toXml()
        cursor.execute("""UPDATE items SET publisher=%s, data=%s
                          FROM nodes
                          WHERE nodes.id = items.node_id AND
                                nodes.node = %s and items.item=%s""",
                       (publisher.full().encode('utf8'),
                        data.encode('utf8'),
                        node_id.encode('utf8'),
                        item["id"].encode('utf8')))
        if cursor.rowcount == 1:
            return

        cursor.execute("""INSERT INTO items (node_id, item, publisher, data)
                          SELECT id, %s, %s, %s FROM nodes WHERE node=%s""",
                       (item["id"].encode('utf8'),
                        publisher.full().encode('utf8'),
                        data.encode('utf8'),
                        node_id.encode('utf8')))

    def add_subscription(self, node_id, subscriber, state):
        return self.dbpool.runInteraction(self._add_subscription, node_id,
                                          subscriber, state)

    def _add_subscription(self, cursor, node_id, subscriber, state):
        self._check_node_exists(cursor, node_id)
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
                            node_id.encode('utf8'),
                            userhost.encode('utf8')))
        except:
            cursor.execute("""SELECT subscription FROM subscriptions
                              JOIN nodes ON (nodes.id=subscriptions.node_id)
                              JOIN entities ON
                                   (entities.id=subscriptions.entity_id)
                              WHERE node=%s AND jid=%s AND resource=%s""",
                           (node_id.encode('utf8'),
                            userhost.encode('utf8'),
                            resource.encode('utf8')))
            state = cursor.fetchone()[0]

        return {'node': node_id,
                'jid': subscriber,
                'subscription': state}

    def remove_subscription(self, node_id, subscriber):
        return self.dbpool.runInteraction(self._remove_subscription, node_id,
                                          subscriber)

    def _remove_subscription(self, cursor, node_id, subscriber):
        self._check_node_exists(cursor, node_id)
        userhost = subscriber.userhost()
        resource = subscriber.resource or ''

        cursor.execute("""DELETE FROM subscriptions WHERE
                          node_id=(SELECT id FROM nodes WHERE node=%s) AND
                          entity_id=(SELECT id FROM entities WHERE jid=%s)
                          AND resource=%s""",
                       (node_id.encode('utf8'),
                        userhost.encode('utf8'),
                        resource.encode('utf8')))
        if cursor.rowcount != 1:
            raise backend.NotSubscribed

        return None

    def create_node(self, node_id, owner):
        return self.dbpool.runInteraction(self._create_node, node_id,
                                          owner)

    def _create_node(self, cursor, node_id, owner):
        try:
            cursor.execute("""INSERT INTO nodes (node) VALUES (%s)""",
                           (node_id.encode('utf8')))
        except:
            raise backend.NodeExists
       
        cursor.execute("""SELECT 1 from entities where jid=%s""",
                       (owner.full().encode('utf8')))

        if not cursor.fetchone():
            cursor.execute("""INSERT INTO entities (jid) VALUES (%s)""",
                           (owner.full().encode('utf8')))

        try:
            cursor.execute("""INSERT INTO affiliations
                              (node_id, entity_id, affiliation)
                              SELECT n.id, e.id, 'owner' FROM
                              (SELECT id FROM nodes WHERE node=%s) AS n
                              CROSS JOIN
                              (SELECT id FROM entities WHERE jid=%s) AS e""",
                           (node_id.encode('utf8'),
                            owner.full().encode('utf8')))
        except Exception, e:
            print e

        return None

    def get_affiliations(self, entity):
        return self.dbpool.runQuery("""SELECT node, affiliation FROM entities
                                       JOIN affiliations ON
                                       (affiliations.entity_id=entities.id)
                                       JOIN nodes ON
                                       (nodes.id=affiliations.node_id)
                                       WHERE jid=%s""",
                                    (entity.full().encode('utf8'),))

    def get_subscriptions(self, entity):
        d = self.dbpool.runQuery("""SELECT node, jid, resource, subscription
                                    FROM entities JOIN subscriptions ON
                                    (subscriptions.entity_id=entities.id)
                                    JOIN nodes ON
                                    (nodes.id=subscriptions.node_id)
                                    WHERE jid=%s""",
                                 (entity.full().encode('utf8'),))
        d.addCallback(self._convert_subscription_jids)
        return d

    def _convert_subscription_jids(self, subscriptions):
        return [(node, jid.JID('%s/%s' % (subscriber, resource)), subscription)
                for node, subscriber, resource, subscription in subscriptions]

    def get_node_type(self, node_id):
        return self.dbpool.runInteraction(self._get_node_type, node_id)
    
    def _get_node_type(self, cursor, node_id):
        self._check_node_exists(cursor, node_id)
        return 'leaf'

    def get_nodes(self):
        d = self.dbpool.runQuery("""SELECT node from nodes""")
        d.addCallback(lambda results: [r[0] for r in results])
        return d

class BackendService(backend.BackendService):
    """ PostgreSQL backend Service for a JEP-0060 pubsub service """

class NodeCreationService(backend.NodeCreationService):
    pass

class PublishService(backend.PublishService):
    pass

class NotificationService(backend.NotificationService):
    pass

class SubscriptionService(backend.SubscriptionService):
    pass

class AffiliationsService(backend.AffiliationsService):
    pass

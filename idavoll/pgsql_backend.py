from twisted.application import service
from twisted.internet import defer
from twisted.protocols.jabber import jid
from twisted.enterprise import adbapi
import backend

class Storage:
    def __init__(self, user, database):
        self.dbpool = adbapi.ConnectionPool('pyPgSQL.PgSQL', user=user,
                database=database)

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
        cursor.execute("""SELECT affiliation FROM affiliations
                          JOIN nodes ON (node_id=nodes.id)
                          JOIN entities ON (entity_id=entities.id)
                          WHERE node=%s AND jid=%s""",
                       (node_id.encode('utf8'), entity.encode('utf8')))

        try:
            return cursor.fetchone()[0]
        except TypeError:
            return None

    def get_affiliation(self, node_id, entity):
        return self.dbpool.runInteraction(self._get_affiliation, node_id,
                                          entity)

    def get_subscribers(self, node_id):
        d =  self.dbpool.runQuery("""SELECT jid, resource FROM subscriptions
                                       JOIN nodes ON (node_id=nodes.id)
                                       JOIN entities ON (entity_id=entities.id)
                                       WHERE node=%s AND
                                             subscription='subscribed'""",
                                    (node_id.encode('utf8'),))
        d.addCallback(self._convert_to_jids)
        return d

    def _convert_to_jids(self, list):
        return [jid.JID("%s/%s" % (l[0], l[1])).full() for l in list]

class BackendService(backend.BackendService):
    """ PostgreSQL backend Service for a JEP-0060 pubsub service """

    def __init__(self, storage):
        backend.BackendService.__init__(self)
        self.storage = storage

    def do_publish(self, result, node_id, items, requestor):
        print result
        configuration = result[0][1]
        persist_items = configuration["persist_items"]
        deliver_payloads = configuration["deliver_payloads"]
        affiliation = result[1][1]

        if affiliation not in ['owner', 'publisher']:
            raise backend.NotAuthorized

        if items and not persist_items and not deliver_payloads:
            raise backend.NoPayloadAllowed
        elif not items and (persist_items or deliver_payloads):
            raise backend.PayloadExpected

        print "publish by %s to %s" % (requestor.full(), node_id)

        if persist_items or deliver_payloads:
            for item in items:
                if item["id"] is None:
                    item["id"] = 'random'   # FIXME

        if persist_items:
            d = self.store_items(node_id, items, requestor.full())
        else:
            d = defer.succeed(None)

        d.addCallback(self.do_notify, node_id, items, deliver_payloads)

    def do_notify(self, result, node_id, items, deliver_payloads):
        if items and not deliver_payloads:
            for item in items:
                item.children = []

        self.dispatch({ 'items': items, 'node_id': node_id },
                      '//event/pubsub/notify')

    def publish(self, node_id, items, requestor):
        d1 = self.storage.get_node_configuration(node_id)
        d2 = self.storage.get_affiliation(node_id, requestor.full())
        d = defer.DeferredList([d1, d2], fireOnOneErrback=1)
        d.addErrback(lambda x: x.value[0])
        d.addCallback(self.do_publish, node_id, items, requestor)
        return d

    def get_notification_list(self, node_id, items):
        d = self.storage.get_subscribers(node_id)
        d.addCallback(self._magic_filter, node_id, items)
        return d

    def _magic_filter(self, subscribers, node_id, items):
        list = {}
        for subscriber in subscribers:
            list[subscriber] = items

        return list

    def store_items(self, node_id, items, publisher):
        return defer.succeed(None)

class PublishService(service.Service):

    __implements__ = backend.IPublishService,
    
    def publish(self, node_id, items, requestor):
        return self.parent.publish(node_id, items, requestor)

class NotificationService(backend.NotificationService):

    __implements__ = backend.INotificationService,

    def get_notification_list(self, node_id, items):
        return self.parent.get_notification_list(node_id, items)

class PersistenceService(service.Service):

    __implements__ = backend.IPersistenceService,

    def store_items(self, node_id, items, publisher):
        return self.parent.store_items(node_id, items, publisher)

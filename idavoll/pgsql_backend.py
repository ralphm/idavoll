from twisted.application import service
from twisted.internet import defer
from twisted.protocols.jabber import jid
from twisted.enterprise import adbapi
import backend

class Service(service.Service):
    """ PostgreSQL backend Service for a JEP-0060 pubsub service """

    __implements__ = backend.IService

    def __init__(self):
        self.dbpool = adbapi.ConnectionPool('pyPgSQL.PgSQL', user='ralphm',
                database='pubsub_test')

    def _do_publish(self, cursor, node_id, publisher, items):
        cursor.execute("""SELECT persistent, deliver_payload FROM nodes
                          WHERE node=%s""",
                       (node_id,))
        try:
            persist_items, deliver_payloads = cursor.fetchone()
        except TypeError:
            raise backend.NodeNotFound

        cursor.execute("""SELECT 1 FROM affiliations
                          JOIN nodes ON (node_id=nodes.id)
                          JOIN entities ON (entity_id=entities.id)
                          WHERE node=%s AND jid=%s AND
                          affiliation IN ('owner', 'publisher')""",
                       (node_id.encode('utf8'), publisher.encode('utf8')))

        if not cursor.fetchone():
            raise backend.NotAuthorized
        
        if items and not persist_items and not deliver_payloads:
            raise backend.NoPayloadAllowed
        elif not items and (persist_items or deliver_payloads):
            raise backend.PayloadExpected

        print "publish by %s to %s" % (publisher, node_id)

        if persist_items or deliver_payloads:
            for item in items:
                if item["id"] is None:
                    item["id"] = 'random'   # FIXME

        if persist_items:
            self.storeItems(node_id, publisher, items)

        if items and not deliver_payloads:
            for item in items:
                item.children = []

        recipients = self.get_subscribers(node_id)
        recipients.addCallback(self.magic_filter, node_id, items)
        recipients.addCallback(self.pubsub_service.do_notification, node_id)

    def do_publish(self, node_id, publisher, items):
        d = self.dbpool.runInteraction(self._do_publish, node_id, publisher, items)
        return d

    def magic_filter(self, subscribers, node_id, items):
        list = {}
        for subscriber in subscribers:
            list[subscriber] = items

        return list

    def get_subscribers(self, node_id):
        d = self.dbpool.runQuery("""SELECT jid, resource FROM subscriptions
                                    JOIN nodes ON (node_id=nodes.id)
                                    JOIN entities ON (entity_id=entities.id)
                                    WHERE node=%s AND
                                          subscription='subscribed'""",
                                 (node_id.encode('utf8'),))
        d.addCallback(self.convert_to_jids)
        return d

    def convert_to_jids(self, list):
        return [jid.JID("%s/%s" % (l[0], l[1])).full() for l in list]

    def storeItems(self, node_id, publisher, items):
        pass

# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

"""
Tests for L{idavoll.gateway}.

Note that some tests are functional tests that require a running idavoll
service.
"""

from twisted.internet import defer
from twisted.trial import unittest
from twisted.web import error
from twisted.words.xish import domish

from idavoll import gateway

AGENT = "Idavoll Test Script"
NS_ATOM = "http://www.w3.org/2005/Atom"

entry = domish.Element((NS_ATOM, 'entry'))
entry.addElement("id", content="urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a")
entry.addElement("title", content="Atom-Powered Robots Run Amok")
entry.addElement("author").addElement("name", content="John Doe")
entry.addElement("content", content="Some text.")

baseURI = "http://localhost:8086/"
componentJID = "pubsub.localhost"

class GatewayTest(unittest.TestCase):
    timeout = 2

    def setUp(self):
        self.client = gateway.GatewayClient(baseURI)
        self.client.startService()

    def tearDown(self):
        self.client.stopService()

    def test_create(self):

        def cb(response):
            self.assertIn('uri', response)

        d = self.client.create()
        d.addCallback(cb)
        return d

    def test_publish(self):

        def cb(response):
            self.assertIn('uri', response)

        d = self.client.publish(entry)
        d.addCallback(cb)
        return d

    def test_publishExistingNode(self):

        def cb2(response, xmppURI):
            self.assertEquals(xmppURI, response['uri'])

        def cb1(response):
            xmppURI = response['uri']
            d = self.client.publish(entry, xmppURI)
            d.addCallback(cb2, xmppURI)
            return d

        d = self.client.create()
        d.addCallback(cb1)
        return d

    def test_publishNonExisting(self):
        def cb(err):
            self.assertEqual('404', err.status)

        d = self.client.publish(entry, 'xmpp:%s?node=test' % componentJID)
        self.assertFailure(d, error.Error)
        d.addCallback(cb)
        return d

    def test_list(self):
        d = self.client.listNodes()
        return d

    def test_subscribe(self):
        def cb(response):
            xmppURI = response['uri']
            d = self.client.subscribe(xmppURI)
            return d

        d = self.client.create()
        d.addCallback(cb)
        return d

    def test_subscribeGetNotification(self):

        def onNotification(data, headers):
            self.client.deferred.callback(None)

        def cb(response):
            xmppURI = response['uri']
            d = self.client.subscribe(xmppURI)
            d.addCallback(lambda _: xmppURI)
            return d

        def cb2(xmppURI):
            d = self.client.publish(entry, xmppURI)
            return d


        self.client.callback = onNotification
        self.client.deferred = defer.Deferred()
        d = self.client.create()
        d.addCallback(cb)
        d.addCallback(cb2)
        return defer.gatherResults([d, self.client.deferred])

    def test_subscribeGetDelayedNotification(self):

        def onNotification(data, headers):
            self.client.deferred.callback(None)

        def cb(response):
            xmppURI = response['uri']
            self.assertNot(self.client.deferred.called)
            d = self.client.publish(entry, xmppURI)
            d.addCallback(lambda _: xmppURI)
            return d

        def cb2(xmppURI):
            d = self.client.subscribe(xmppURI)
            return d


        self.client.callback = onNotification
        self.client.deferred = defer.Deferred()
        d = self.client.create()
        d.addCallback(cb)
        d.addCallback(cb2)
        return defer.gatherResults([d, self.client.deferred])

    def test_subscribeGetDelayedNotification2(self):
        """
        Test that subscribing as second results in a notification being sent.
        """

        def onNotification1(data, headers):
            client1.deferred.callback(None)
            client1.stopService()

        def onNotification2(data, headers):
            client2.deferred.callback(None)
            client2.stopService()

        def cb(response):
            xmppURI = response['uri']
            self.assertNot(client1.deferred.called)
            self.assertNot(client2.deferred.called)
            d = self.client.publish(entry, xmppURI)
            d.addCallback(lambda _: xmppURI)
            return d

        def cb2(xmppURI):
            d = client1.subscribe(xmppURI)
            d.addCallback(lambda _: xmppURI)
            return d

        def cb3(xmppURI):
            d = client2.subscribe(xmppURI)
            return d

        client1 = gateway.GatewayClient(baseURI, callbackPort=8088)
        client1.startService()
        client1.callback = onNotification1
        client1.deferred = defer.Deferred()
        client2 = gateway.GatewayClient(baseURI, callbackPort=8089)
        client2.startService()
        client2.callback = onNotification2
        client2.deferred = defer.Deferred()


        d = self.client.create()
        d.addCallback(cb)
        d.addCallback(cb2)
        d.addCallback(cb3)
        dl = defer.gatherResults([d, client1.deferred, client2.deferred])
        return dl


    def test_subscribeNonExisting(self):
        def cb(err):
            self.assertEqual('403', err.status)

        d = self.client.subscribe('xmpp:%s?node=test' % componentJID)
        self.assertFailure(d, error.Error)
        d.addCallback(cb)
        return d


    def test_unsubscribeNonExisting(self):
        def cb(err):
            self.assertEqual('403', err.status)

        d = self.client.unsubscribe('xmpp:%s?node=test' % componentJID)
        self.assertFailure(d, error.Error)
        d.addCallback(cb)
        return d


    def test_items(self):
        def cb(response):
            xmppURI = response['uri']
            d = self.client.items(xmppURI)
            return d

        d = self.client.publish(entry)
        d.addCallback(cb)
        return d


    def test_itemsMaxItems(self):
        def cb(response):
            xmppURI = response['uri']
            d = self.client.items(xmppURI, 2)
            return d

        d = self.client.publish(entry)
        d.addCallback(cb)
        return d

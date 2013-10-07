# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Tests for L{idavoll.gateway}.

Note that some tests are functional tests that require a running idavoll
service.
"""

from StringIO import StringIO

import simplejson

from twisted.internet import defer
from twisted.trial import unittest
from twisted.web import error, http, http_headers, server
from twisted.web.test import requesthelper
from twisted.words.xish import domish
from twisted.words.protocols.jabber.jid import JID

from idavoll import gateway
from idavoll.backend import BackendService
from idavoll.memory_storage import Storage

AGENT = "Idavoll Test Script"
NS_ATOM = "http://www.w3.org/2005/Atom"

TEST_ENTRY = domish.Element((NS_ATOM, 'entry'))
TEST_ENTRY.addElement("id",
                      content="urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a")
TEST_ENTRY.addElement("title", content="Atom-Powered Robots Run Amok")
TEST_ENTRY.addElement("author").addElement("name", content="John Doe")
TEST_ENTRY.addElement("content", content="Some text.")

baseURI = "http://localhost:8086/"
component = "pubsub"
componentJID = JID(component)
ownerJID = JID('owner@example.org')

def _render(resource, request):
    result = resource.render(request)
    if isinstance(result, str):
        request.write(result)
        request.finish()
        return defer.succeed(None)
    elif result is server.NOT_DONE_YET:
        if request.finished:
            return defer.succeed(None)
        else:
            return request.notifyFinish()
    else:
        raise ValueError("Unexpected return value: %r" % (result,))


class DummyRequest(requesthelper.DummyRequest):

    def __init__(self, *args, **kwargs):
        requesthelper.DummyRequest.__init__(self, *args, **kwargs)
        self.requestHeaders = http_headers.Headers()



class GetServiceAndNodeTest(unittest.TestCase):
    """
    Tests for {gateway.getServiceAndNode}.
    """

    def test_basic(self):
        """
        getServiceAndNode parses an XMPP URI with node parameter.
        """
        uri = b'xmpp:pubsub.example.org?;node=test'
        service, nodeIdentifier = gateway.getServiceAndNode(uri)
        self.assertEqual(JID(u'pubsub.example.org'), service)
        self.assertEqual(u'test', nodeIdentifier)


    def test_schemeEmpty(self):
        """
        If the URI scheme is empty, an exception is raised.
        """
        uri = b'pubsub.example.org'
        self.assertRaises(gateway.XMPPURIParseError,
                          gateway.getServiceAndNode, uri)


    def test_schemeNotXMPP(self):
        """
        If the URI scheme is not 'xmpp', an exception is raised.
        """
        uri = b'mailto:test@example.org'
        self.assertRaises(gateway.XMPPURIParseError,
                          gateway.getServiceAndNode, uri)


    def test_authorityPresent(self):
        """
        If the URI has an authority component, an exception is raised.
        """
        uri = b'xmpp://pubsub.example.org/'
        self.assertRaises(gateway.XMPPURIParseError,
                          gateway.getServiceAndNode, uri)


    def test_queryEmpty(self):
        """
        If there is no query component, the nodeIdentifier is empty.
        """
        uri = b'xmpp:pubsub.example.org'
        service, nodeIdentifier = gateway.getServiceAndNode(uri)

        self.assertEqual(JID(u'pubsub.example.org'), service)
        self.assertEqual(u'', nodeIdentifier)


    def test_jidInvalid(self):
        """
        If the JID from the path component is invalid, an exception is raised.
        """
        uri = b'xmpp:@@pubsub.example.org?;node=test'
        self.assertRaises(gateway.XMPPURIParseError,
                          gateway.getServiceAndNode, uri)


    def test_pathEmpty(self):
        """
        If there is no path component, an exception is raised.
        """
        uri = b'xmpp:?node=test'
        self.assertRaises(gateway.XMPPURIParseError,
                          gateway.getServiceAndNode, uri)


    def test_nodeAbsent(self):
        """
        If the node parameter is missing, the nodeIdentifier is empty.
        """
        uri = b'xmpp:pubsub.example.org?'
        service, nodeIdentifier = gateway.getServiceAndNode(uri)

        self.assertEqual(JID(u'pubsub.example.org'), service)
        self.assertEqual(u'', nodeIdentifier)



class GetXMPPURITest(unittest.TestCase):
    """
    Tests for L{gateway.getXMPPURITest}.
    """

    def test_basic(self):
        uri = gateway.getXMPPURI(JID(u'pubsub.example.org'), u'test')
        self.assertEqual('xmpp:pubsub.example.org?;node=test', uri)


class CreateResourceTest(unittest.TestCase):
    """
    Tests for L{gateway.CreateResource}.
    """

    def setUp(self):
        self.backend = BackendService(Storage())
        self.resource = gateway.CreateResource(self.backend, componentJID,
                                               ownerJID)


    def test_get(self):
        """
        The method GET is not supported.
        """
        request = DummyRequest([b''])
        self.assertRaises(error.UnsupportedMethod,
                          _render, self.resource, request)


    def test_post(self):
        """
        Upon a POST, a new node is created and the URI returned.
        """
        request = DummyRequest([b''])
        request.method = 'POST'

        def gotNodes(nodeIdentifiers, uri):
            service, nodeIdentifier = gateway.getServiceAndNode(uri)
            self.assertIn(nodeIdentifier, nodeIdentifiers)

        def rendered(result):
            self.assertEqual('application/json',
                             request.outgoingHeaders['content-type'])
            payload = simplejson.loads(b''.join(request.written))
            self.assertIn('uri', payload)
            d = self.backend.getNodes()
            d.addCallback(gotNodes, payload['uri'])
            return d

        d = _render(self.resource, request)
        d.addCallback(rendered)
        return d



class DeleteResourceTest(unittest.TestCase):
    """
    Tests for L{gateway.DeleteResource}.
    """

    def setUp(self):
        self.backend = BackendService(Storage())
        self.resource = gateway.DeleteResource(self.backend, componentJID,
                                               ownerJID)


    def test_get(self):
        """
        The method GET is not supported.
        """
        request = DummyRequest([b''])
        self.assertRaises(error.UnsupportedMethod,
                          _render, self.resource, request)


    def test_post(self):
        """
        Upon a POST, a new node is created and the URI returned.
        """
        request = DummyRequest([b''])
        request.method = b'POST'

        def rendered(result):
            self.assertEqual(http.NO_CONTENT, request.responseCode)

        def nodeCreated(nodeIdentifier):
            uri = gateway.getXMPPURI(componentJID, nodeIdentifier)
            request.args[b'uri'] = [uri]
            request.content = StringIO(b'')

            return _render(self.resource, request)

        d = self.backend.createNode(u'test', ownerJID)
        d.addCallback(nodeCreated)
        d.addCallback(rendered)
        return d


    def test_postWithRedirect(self):
        """
        Upon a POST, a new node is created and the URI returned.
        """
        request = DummyRequest([b''])
        request.method = b'POST'
        otherNodeURI = b'xmpp:pubsub.example.org?node=other'

        def rendered(result):
            self.assertEqual(http.NO_CONTENT, request.responseCode)
            self.assertEqual(1, len(deletes))
            nodeIdentifier, owner, redirectURI = deletes[-1]
            self.assertEqual(otherNodeURI, redirectURI)

        def nodeCreated(nodeIdentifier):
            uri = gateway.getXMPPURI(componentJID, nodeIdentifier)
            request.args[b'uri'] = [uri]
            payload = {b'redirect_uri': otherNodeURI}
            body = simplejson.dumps(payload)
            request.content = StringIO(body)
            return _render(self.resource, request)

        def deleteNode(nodeIdentifier, owner, redirectURI):
            deletes.append((nodeIdentifier, owner, redirectURI))
            return defer.succeed(nodeIdentifier)

        deletes = []
        self.patch(self.backend, 'deleteNode', deleteNode)
        d = self.backend.createNode(u'test', ownerJID)
        d.addCallback(nodeCreated)
        d.addCallback(rendered)
        return d


    def test_postUnknownNode(self):
        """
        If the node to be deleted is unknown, 404 Not Found is returned.
        """
        request = DummyRequest([b''])
        request.method = b'POST'

        def rendered(result):
            self.assertEqual(http.NOT_FOUND, request.responseCode)

        uri = gateway.getXMPPURI(componentJID, u'unknown')
        request.args[b'uri'] = [uri]
        request.content = StringIO(b'')

        d = _render(self.resource, request)
        d.addCallback(rendered)
        return d


    def test_postMalformedXMPPURI(self):
        """
        If the XMPP URI is malformed, Bad Request is returned.
        """
        request = DummyRequest([b''])
        request.method = b'POST'

        def rendered(result):
            self.assertEqual(http.BAD_REQUEST, request.responseCode)

        uri = 'xmpp:@@@@'
        request.args[b'uri'] = [uri]
        request.content = StringIO(b'')

        d = _render(self.resource, request)
        d.addCallback(rendered)
        return d


    def test_postURIMissing(self):
        """
        If no URI is passed, 400 Bad Request is returned.
        """
        request = DummyRequest([b''])
        request.method = b'POST'

        def rendered(result):
            self.assertEqual(http.BAD_REQUEST, request.responseCode)

        request.content = StringIO(b'')

        d = _render(self.resource, request)
        d.addCallback(rendered)
        return d



class CallbackResourceTest(unittest.TestCase):
    """
    Tests for L{gateway.CallbackResource}.
    """

    def setUp(self):
        self.callbackEvents = []
        self.resource = gateway.CallbackResource(self._callback)


    def _callback(self, payload, headers):
        self.callbackEvents.append((payload, headers))


    def test_get(self):
        """
        The method GET is not supported.
        """
        request = DummyRequest([b''])
        self.assertRaises(error.UnsupportedMethod,
                          _render, self.resource, request)


    def test_post(self):
        """
        The body posted is passed to the callback.
        """
        request = DummyRequest([b''])
        request.method = 'POST'
        request.content = StringIO(b'<root><child/></root>')

        def rendered(result):
            self.assertEqual(1, len(self.callbackEvents))
            payload, headers = self.callbackEvents[-1]
            self.assertEqual('root', payload.name)

            self.assertEqual(http.NO_CONTENT, request.responseCode)
            self.assertFalse(b''.join(request.written))

        d = _render(self.resource, request)
        d.addCallback(rendered)
        return d


    def test_postEvent(self):
        """
        If the Event header is set, the payload is empty and the header passed.
        """
        request = DummyRequest([b''])
        request.method = 'POST'
        request.requestHeaders.addRawHeader(b'Event', b'DELETE')
        request.content = StringIO(b'')

        def rendered(result):
            self.assertEqual(1, len(self.callbackEvents))
            payload, headers = self.callbackEvents[-1]
            self.assertIdentical(None, payload)
            self.assertEqual(['DELETE'], headers.getRawHeaders(b'Event'))
            self.assertFalse(b''.join(request.written))

        d = _render(self.resource, request)
        d.addCallback(rendered)
        return d



class GatewayTest(unittest.TestCase):
    timeout = 2

    def setUp(self):
        self.client = gateway.GatewayClient(baseURI)
        self.client.startService()
        self.addCleanup(self.client.stopService)

        def trapConnectionRefused(failure):
            from twisted.internet.error import ConnectionRefusedError
            failure.trap(ConnectionRefusedError)
            raise unittest.SkipTest("Gateway to test against is not available")

        def trapNotFound(failure):
            from twisted.web.error import Error
            failure.trap(Error)

        d = self.client.ping()
        d.addErrback(trapConnectionRefused)
        d.addErrback(trapNotFound)
        return d


    def tearDown(self):
        return self.client.stopService()


    def test_create(self):

        def cb(response):
            self.assertIn('uri', response)

        d = self.client.create()
        d.addCallback(cb)
        return d

    def test_publish(self):

        def cb(response):
            self.assertIn('uri', response)

        d = self.client.publish(TEST_ENTRY)
        d.addCallback(cb)
        return d

    def test_publishExistingNode(self):

        def cb2(response, xmppURI):
            self.assertEquals(xmppURI, response['uri'])

        def cb1(response):
            xmppURI = response['uri']
            d = self.client.publish(TEST_ENTRY, xmppURI)
            d.addCallback(cb2, xmppURI)
            return d

        d = self.client.create()
        d.addCallback(cb1)
        return d

    def test_publishNonExisting(self):
        def cb(err):
            self.assertEqual('404', err.status)

        d = self.client.publish(TEST_ENTRY, 'xmpp:%s?node=test' % component)
        self.assertFailure(d, error.Error)
        d.addCallback(cb)
        return d

    def test_delete(self):
        def cb(response):
            xmppURI = response['uri']
            d = self.client.delete(xmppURI)
            return d

        d = self.client.create()
        d.addCallback(cb)
        return d

    def test_deleteWithRedirect(self):
        def cb(response):
            xmppURI = response['uri']
            redirectURI = 'xmpp:%s?node=test' % component
            d = self.client.delete(xmppURI, redirectURI)
            return d

        d = self.client.create()
        d.addCallback(cb)
        return d

    def test_deleteNotification(self):
        def onNotification(data, headers):
            try:
                self.assertTrue(headers.hasHeader('Event'))
                self.assertEquals(['DELETED'], headers.getRawHeaders('Event'))
                self.assertFalse(headers.hasHeader('Link'))
            except:
                self.client.deferred.errback()
            else:
                self.client.deferred.callback(None)

        def cb(response):
            xmppURI = response['uri']
            d = self.client.subscribe(xmppURI)
            d.addCallback(lambda _: xmppURI)
            return d

        def cb2(xmppURI):
            d = self.client.delete(xmppURI)
            return d

        self.client.callback = onNotification
        self.client.deferred = defer.Deferred()
        d = self.client.create()
        d.addCallback(cb)
        d.addCallback(cb2)
        return defer.gatherResults([d, self.client.deferred])

    def test_deleteNotificationWithRedirect(self):
        redirectURI = 'xmpp:%s?node=test' % component

        def onNotification(data, headers):
            try:
                self.assertTrue(headers.hasHeader('Event'))
                self.assertEquals(['DELETED'], headers.getRawHeaders('Event'))
                self.assertEquals(['<%s>; rel=alternate' % redirectURI],
                                  headers.getRawHeaders('Link'))
            except:
                self.client.deferred.errback()
            else:
                self.client.deferred.callback(None)

        def cb(response):
            xmppURI = response['uri']
            d = self.client.subscribe(xmppURI)
            d.addCallback(lambda _: xmppURI)
            return d

        def cb2(xmppURI):
            d = self.client.delete(xmppURI, redirectURI)
            return d

        self.client.callback = onNotification
        self.client.deferred = defer.Deferred()
        d = self.client.create()
        d.addCallback(cb)
        d.addCallback(cb2)
        return defer.gatherResults([d, self.client.deferred])

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
            d = self.client.publish(TEST_ENTRY, xmppURI)
            return d


        self.client.callback = onNotification
        self.client.deferred = defer.Deferred()
        d = self.client.create()
        d.addCallback(cb)
        d.addCallback(cb2)
        return defer.gatherResults([d, self.client.deferred])


    def test_subscribeTwiceGetNotification(self):

        def onNotification1(data, headers):
            d = client1.stopService()
            d.chainDeferred(client1.deferred)

        def onNotification2(data, headers):
            d = client2.stopService()
            d.chainDeferred(client2.deferred)

        def cb(response):
            xmppURI = response['uri']
            d = client1.subscribe(xmppURI)
            d.addCallback(lambda _: xmppURI)
            return d

        def cb2(xmppURI):
            d = client2.subscribe(xmppURI)
            d.addCallback(lambda _: xmppURI)
            return d

        def cb3(xmppURI):
            d = self.client.publish(TEST_ENTRY, xmppURI)
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


    def test_subscribeGetDelayedNotification(self):

        def onNotification(data, headers):
            self.client.deferred.callback(None)

        def cb(response):
            xmppURI = response['uri']
            self.assertNot(self.client.deferred.called)
            d = self.client.publish(TEST_ENTRY, xmppURI)
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
            d = self.client.publish(TEST_ENTRY, xmppURI)
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

        d = self.client.subscribe('xmpp:%s?node=test' % component)
        self.assertFailure(d, error.Error)
        d.addCallback(cb)
        return d


    def test_subscribeRootGetNotification(self):

        def clean(rootNode):
            return self.client.unsubscribe(rootNode)

        def onNotification(data, headers):
            self.client.deferred.callback(None)

        def cb(response):
            xmppURI = response['uri']
            jid, nodeIdentifier = gateway.getServiceAndNode(xmppURI)
            rootNode = gateway.getXMPPURI(jid, '')

            d = self.client.subscribe(rootNode)
            d.addCallback(lambda _: self.addCleanup(clean, rootNode))
            d.addCallback(lambda _: xmppURI)
            return d

        def cb2(xmppURI):
            return self.client.publish(TEST_ENTRY, xmppURI)


        self.client.callback = onNotification
        self.client.deferred = defer.Deferred()
        d = self.client.create()
        d.addCallback(cb)
        d.addCallback(cb2)
        return defer.gatherResults([d, self.client.deferred])


    def test_unsubscribeNonExisting(self):
        def cb(err):
            self.assertEqual('403', err.status)

        d = self.client.unsubscribe('xmpp:%s?node=test' % component)
        self.assertFailure(d, error.Error)
        d.addCallback(cb)
        return d


    def test_items(self):
        def cb(response):
            xmppURI = response['uri']
            d = self.client.items(xmppURI)
            return d

        d = self.client.publish(TEST_ENTRY)
        d.addCallback(cb)
        return d


    def test_itemsMaxItems(self):
        def cb(response):
            xmppURI = response['uri']
            d = self.client.items(xmppURI, 2)
            return d

        d = self.client.publish(TEST_ENTRY)
        d.addCallback(cb)
        return d

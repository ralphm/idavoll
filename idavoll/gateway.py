# -*- test-case-name: idavoll.test.test_gateway -*-
#
# Copyright (c) Ralph Meijer.
# See LICENSE for details.

"""
Web resources and client for interacting with pubsub services.
"""

import mimetools
from time import gmtime, strftime
from StringIO import StringIO
import urllib
import urlparse

import simplejson

from twisted.application import service
from twisted.internet import defer, reactor
from twisted.python import log
from twisted.web import client, http, resource, server
from twisted.web.error import Error
from twisted.words.protocols.jabber.jid import JID
from twisted.words.protocols.jabber.error import StanzaError
from twisted.words.xish import domish

from wokkel.generic import parseXml
from wokkel.pubsub import Item
from wokkel.pubsub import PubSubClient

from idavoll import error

NS_ATOM = 'http://www.w3.org/2005/Atom'
MIME_ATOM_ENTRY = b'application/atom+xml;type=entry'
MIME_ATOM_FEED = b'application/atom+xml;type=feed'
MIME_JSON = b'application/json'

class XMPPURIParseError(ValueError):
    """
    Raised when a given XMPP URI couldn't be properly parsed.
    """



def getServiceAndNode(uri):
    """
    Given an XMPP URI, extract the publish subscribe service JID and node ID.
    """

    try:
        scheme, rest = uri.split(':', 1)
    except ValueError:
        raise XMPPURIParseError("No URI scheme component")

    if scheme != 'xmpp':
        raise XMPPURIParseError("Unknown URI scheme")

    if rest.startswith("//"):
        raise XMPPURIParseError("Unexpected URI authority component")

    try:
        entity, query = rest.split('?', 1)
    except ValueError:
        entity, query = rest, ''

    if not entity:
        raise XMPPURIParseError("Empty URI path component")

    try:
        service = JID(entity)
    except Exception, e:
        raise XMPPURIParseError("Invalid JID: %s" % e)

    params = urlparse.parse_qs(query)

    try:
        nodeIdentifier = params['node'][0]
    except (KeyError, ValueError):
        nodeIdentifier = ''

    return service, nodeIdentifier



def getXMPPURI(service, nodeIdentifier):
    """
    Construct an XMPP URI from a service JID and node identifier.
    """
    return "xmpp:%s?;node=%s" % (service.full(), nodeIdentifier or '')



def _parseContentType(header):
    """
    Parse a Content-Type header value to a L{mimetools.Message}.

    L{mimetools.Message} parses a Content-Type header and makes the
    components available with its C{getmaintype}, C{getsubtype}, C{gettype},
    C{getplist} and C{getparam} methods.
    """
    return mimetools.Message(StringIO(b'Content-Type: ' + header))



def _asyncResponse(render):
    """
    """
    def wrapped(self, request):
        def eb(failure):
            if failure.check(Error):
                err = failure.value
            else:
                log.err(failure)
                err = Error(500)
            request.setResponseCode(err.status, err.message)
            return err.response

        def finish(result):
            if result is server.NOT_DONE_YET:
                return

            if result:
                request.write(result)
            request.finish()

        d = defer.maybeDeferred(render, self, request)
        d.addErrback(eb)
        d.addCallback(finish)

        return server.NOT_DONE_YET

    return wrapped



class CreateResource(resource.Resource):
    """
    A resource to create a publish-subscribe node.
    """
    def __init__(self, backend, serviceJID, owner):
        self.backend = backend
        self.serviceJID = serviceJID
        self.owner = owner


    http_GET = None


    @_asyncResponse
    def render_POST(self, request):
        """
        Respond to a POST request to create a new node.
        """

        def toResponse(nodeIdentifier):
            uri = getXMPPURI(self.serviceJID, nodeIdentifier)
            body = simplejson.dumps({'uri': uri})
            request.setHeader(b'Content-Type', MIME_JSON)
            return body

        d = self.backend.createNode(None, self.owner)
        d.addCallback(toResponse)
        return d



class DeleteResource(resource.Resource):
    """
    A resource to create a publish-subscribe node.
    """
    def __init__(self, backend, serviceJID, owner):
        self.backend = backend
        self.serviceJID = serviceJID
        self.owner = owner


    render_GET = None


    @_asyncResponse
    def render_POST(self, request):
        """
        Respond to a POST request to create a new node.
        """
        def toResponse(result):
            request.setResponseCode(http.NO_CONTENT)

        def trapNotFound(failure):
            failure.trap(error.NodeNotFound)
            raise Error(http.NOT_FOUND, "Node not found")

        if not request.args.get('uri'):
            raise Error(http.BAD_REQUEST, "No URI given")

        try:
            jid, nodeIdentifier = getServiceAndNode(request.args['uri'][0])
        except XMPPURIParseError, e:
            raise Error(http.BAD_REQUEST, "Malformed XMPP URI: %s" % e)


        data = request.content.read()
        if data:
            params = simplejson.loads(data)
            redirectURI = params.get('redirect_uri', None)
        else:
            redirectURI = None

        d = self.backend.deleteNode(nodeIdentifier, self.owner,
                                    redirectURI)
        d.addCallback(toResponse)
        d.addErrback(trapNotFound)
        return d



class PublishResource(resource.Resource):
    """
    A resource to publish to a publish-subscribe node.
    """

    def __init__(self, backend, serviceJID, owner):
        self.backend = backend
        self.serviceJID = serviceJID
        self.owner = owner


    render_GET = None


    def checkMediaType(self, request):
        ctype = request.getHeader(b'content-type')

        if not ctype:
            request.setResponseCode(http.BAD_REQUEST)

            raise Error(http.BAD_REQUEST, b"No specified Media Type")

        message = _parseContentType(ctype)
        if (message.maintype != b'application' or
            message.subtype != b'atom+xml' or
            message.getparam(b'type') != b'entry' or
            (message.getparam(b'charset') or b'utf-8') != b'utf-8'):
            raise Error(http.UNSUPPORTED_MEDIA_TYPE,
                              b"Unsupported Media Type: %s" % ctype)


    @_asyncResponse
    def render_POST(self, request):
        """
        Respond to a POST request to create a new item.
        """

        def toResponse(nodeIdentifier):
            uri = getXMPPURI(self.serviceJID, nodeIdentifier)
            body = simplejson.dumps({'uri': uri})
            request.setHeader(b'Content-Type', MIME_JSON)
            return body

        def gotNode(nodeIdentifier, payload):
            item = Item(id='current', payload=payload)
            d = self.backend.publish(nodeIdentifier, [item], self.owner)
            d.addCallback(lambda _: nodeIdentifier)
            return d

        def getNode():
            if request.args.get('uri'):
                jid, nodeIdentifier = getServiceAndNode(request.args['uri'][0])
                return defer.succeed(nodeIdentifier)
            else:
                return self.backend.createNode(None, self.owner)

        def trapNotFound(failure):
            failure.trap(error.NodeNotFound)
            raise Error(http.NOT_FOUND, "Node not found")

        def trapXMPPURIParseError(failure):
            failure.trap(XMPPURIParseError)
            raise Error(http.BAD_REQUEST,
                        "Malformed XMPP URI: %s" % failure.value)

        self.checkMediaType(request)
        payload = parseXml(request.content.read())
        d = getNode()
        d.addCallback(gotNode, payload)
        d.addCallback(toResponse)
        d.addErrback(trapNotFound)
        d.addErrback(trapXMPPURIParseError)
        return d



class ListResource(resource.Resource):
    def __init__(self, service):
        self.service = service


    @_asyncResponse
    def render_GET(self, request):
        def responseFromNodes(nodeIdentifiers):
            body = simplejson.dumps(nodeIdentifiers)
            request.setHeader(b'Content-Type', MIME_JSON)
            return body

        d = self.service.getNodes()
        d.addCallback(responseFromNodes)
        return d



# Service for subscribing to remote XMPP Pubsub nodes and web resources

def extractAtomEntries(items):
    """
    Extract atom entries from a list of publish-subscribe items.

    @param items: List of L{domish.Element}s that represent publish-subscribe
        items.
    @type items: C{list}
    """

    atomEntries = []

    for item in items:
        # ignore non-items (i.e. retractions)
        if item.name != 'item':
            continue

        atomEntry = None
        for element in item.elements():
            # extract the first element that is an atom entry
            if element.uri == NS_ATOM and element.name == 'entry':
                atomEntry = element
                break

        if atomEntry:
            atomEntries.append(atomEntry)

    return atomEntries



def constructFeed(service, nodeIdentifier, entries, title):
    nodeURI = getXMPPURI(service, nodeIdentifier)
    now = strftime("%Y-%m-%dT%H:%M:%SZ", gmtime())

    # Collect the received entries in a feed
    feed = domish.Element((NS_ATOM, 'feed'))
    feed.addElement('title', content=title)
    feed.addElement('id', content=nodeURI)
    feed.addElement('updated', content=now)

    for entry in entries:
        feed.addChild(entry)

    return feed



class RemoteSubscriptionService(service.Service, PubSubClient):
    """
    Service for subscribing to remote XMPP Publish-Subscribe nodes.

    Subscriptions are created with a callback HTTP URI that is POSTed
    to with the received items in notifications.
    """

    def __init__(self, jid, storage):
        self.jid = jid
        self.storage = storage


    def trapNotFound(self, failure):
        failure.trap(StanzaError)

        if failure.value.condition == 'item-not-found':
            raise error.NodeNotFound()
        else:
            return failure


    def subscribeCallback(self, jid, nodeIdentifier, callback):
        """
        Subscribe a callback URI.

        This registers a callback URI to be called when a notification is
        received for the given node.

        If this is the first callback registered for this node, the gateway
        will subscribe to the node. Otherwise, the most recently published item
        for this node is retrieved and, if present, the newly registered
        callback will be called with that item.
        """

        def callbackForLastItem(items):
            atomEntries = extractAtomEntries(items)

            if not atomEntries:
                return

            self._postTo([callback], jid, nodeIdentifier, atomEntries[0],
                         MIME_ATOM_ENTRY)

        def subscribeOrItems(hasCallbacks):
            if hasCallbacks:
                if not nodeIdentifier:
                    return None
                d = self.items(jid, nodeIdentifier, 1)
                d.addCallback(callbackForLastItem)
            else:
                d = self.subscribe(jid, nodeIdentifier, self.jid)

            d.addErrback(self.trapNotFound)
            return d

        d = self.storage.hasCallbacks(jid, nodeIdentifier)
        d.addCallback(subscribeOrItems)
        d.addCallback(lambda _: self.storage.addCallback(jid, nodeIdentifier,
                                                         callback))
        return d


    def unsubscribeCallback(self, jid, nodeIdentifier, callback):
        """
        Unsubscribe a callback.

        If this was the last registered callback for this node, the
        gateway will unsubscribe from node.
        """

        def cb(last):
            if last:
                return self.unsubscribe(jid, nodeIdentifier, self.jid)

        d = self.storage.removeCallback(jid, nodeIdentifier, callback)
        d.addCallback(cb)
        return d


    def itemsReceived(self, event):
        """
        Fire up HTTP client to do callback
        """

        atomEntries = extractAtomEntries(event.items)
        service = event.sender
        nodeIdentifier = event.nodeIdentifier
        headers = event.headers

        # Don't notify if there are no atom entries
        if not atomEntries:
            return

        if len(atomEntries) == 1:
            contentType = MIME_ATOM_ENTRY
            payload = atomEntries[0]
        else:
            contentType = MIME_ATOM_FEED
            payload = constructFeed(service, nodeIdentifier, atomEntries,
                                    title='Received item collection')

        self.callCallbacks(service, nodeIdentifier, payload, contentType)

        if 'Collection' in headers:
            for collection in headers['Collection']:
                nodeIdentifier = collection or ''
                self.callCallbacks(service, nodeIdentifier, payload,
                                   contentType)


    def deleteReceived(self, event):
        """
        Fire up HTTP client to do callback
        """

        service = event.sender
        nodeIdentifier = event.nodeIdentifier
        redirectURI = event.redirectURI
        self.callCallbacks(service, nodeIdentifier, eventType='DELETED',
                           redirectURI=redirectURI)


    def _postTo(self, callbacks, service, nodeIdentifier,
                      payload=None, contentType=None, eventType=None,
                      redirectURI=None):

        if not callbacks:
            return

        postdata = None
        nodeURI = getXMPPURI(service, nodeIdentifier)
        headers = {'Referer': nodeURI.encode('utf-8'),
                   'PubSub-Service': service.full().encode('utf-8')}

        if payload:
            postdata = payload.toXml().encode('utf-8')
            if contentType:
                headers['Content-Type'] = "%s;charset=utf-8" % contentType

        if eventType:
            headers['Event'] = eventType

        if redirectURI:
            headers['Link'] = '<%s>; rel=alternate' % (
                              redirectURI.encode('utf-8'),
                              )

        def postNotification(callbackURI):
            f = getPageWithFactory(str(callbackURI),
                                   method='POST',
                                   postdata=postdata,
                                   headers=headers)
            d = f.deferred
            d.addErrback(log.err)

        for callbackURI in callbacks:
            reactor.callLater(0, postNotification, callbackURI)


    def callCallbacks(self, service, nodeIdentifier,
                            payload=None, contentType=None, eventType=None,
                            redirectURI=None):

        def eb(failure):
            failure.trap(error.NoCallbacks)

            # No callbacks were registered for this node. Unsubscribe?

        d = self.storage.getCallbacks(service, nodeIdentifier)
        d.addCallback(self._postTo, service, nodeIdentifier, payload,
                                    contentType, eventType, redirectURI)
        d.addErrback(eb)
        d.addErrback(log.err)



class RemoteSubscribeBaseResource(resource.Resource):
    """
    Base resource for remote pubsub node subscription and unsubscription.

    This resource accepts POST request with a JSON document that holds
    a dictionary with the keys C{uri} and C{callback} that respectively map
    to the XMPP URI of the publish-subscribe node and the callback URI.

    This class should be inherited with L{serviceMethod} overridden.

    @cvar serviceMethod: The name of the method to be called with
                         the JID of the pubsub service, the node identifier
                         and the callback URI as received in the HTTP POST
                         request to this resource.
    """
    serviceMethod = None
    errorMap = {
            error.NodeNotFound:
                (http.FORBIDDEN, "Node not found"),
            error.NotSubscribed:
                (http.FORBIDDEN, "No such subscription found"),
            error.SubscriptionExists:
                (http.FORBIDDEN, "Subscription already exists"),
    }

    def __init__(self, service):
        self.service = service
        self.params = None


    render_GET = None


    @_asyncResponse
    def render_POST(self, request):
        def trapNotFound(failure):
            err = failure.trap(*self.errorMap.keys())
            status, message = self.errorMap[err]
            raise Error(status, message)

        def toResponse(result):
            request.setResponseCode(http.NO_CONTENT)
            return b''

        def trapXMPPURIParseError(failure):
            failure.trap(XMPPURIParseError)
            raise Error(http.BAD_REQUEST,
                        "Malformed XMPP URI: %s" % failure.value)

        data = request.content.read()
        self.params = simplejson.loads(data)

        uri = self.params['uri']
        callback = self.params['callback']

        jid, nodeIdentifier = getServiceAndNode(uri)
        method = getattr(self.service, self.serviceMethod)
        d = method(jid, nodeIdentifier, callback)
        d.addCallback(toResponse)
        d.addErrback(trapNotFound)
        d.addErrback(trapXMPPURIParseError)
        return d



class RemoteSubscribeResource(RemoteSubscribeBaseResource):
    """
    Resource to subscribe to a remote publish-subscribe node.

    The passed C{uri} is the XMPP URI of the node to subscribe to and the
    C{callback} is the callback URI. Upon receiving notifications from the
    node, a POST request will be perfomed on the callback URI.
    """
    serviceMethod = 'subscribeCallback'



class RemoteUnsubscribeResource(RemoteSubscribeBaseResource):
    """
    Resource to unsubscribe from a remote publish-subscribe node.

    The passed C{uri} is the XMPP URI of the node to unsubscribe from and the
    C{callback} is the callback URI that was registered for it.
    """
    serviceMethod = 'unsubscribeCallback'



class RemoteItemsResource(resource.Resource):
    """
    Resource for retrieving items from a remote pubsub node.
    """

    def __init__(self, service):
        self.service = service


    @_asyncResponse
    def render_GET(self, request):
        try:
            maxItems = int(request.args.get('max_items', [0])[0]) or None
        except ValueError:
            raise Error(http.BAD_REQUEST,
                        "The argument max_items has an invalid value.")

        try:
            uri = request.args['uri'][0]
        except KeyError:
            raise Error(http.BAD_REQUEST,
                        "No URI for the remote node provided.")

        try:
            jid, nodeIdentifier = getServiceAndNode(uri)
        except XMPPURIParseError:
            raise Error(http.BAD_REQUEST,
                        "Malformed XMPP URI: %s" % uri)

        def toResponse(items):
            """
            Create a feed out the retrieved items.
            """
            atomEntries = extractAtomEntries(items)
            feed = constructFeed(jid, nodeIdentifier, atomEntries,
                                    "Retrieved item collection")
            body = feed.toXml().encode('utf-8')
            request.setHeader(b'Content-Type', MIME_ATOM_FEED)
            return body

        def trapNotFound(failure):
            failure.trap(StanzaError)
            if not failure.value.condition == 'item-not-found':
                raise failure
            raise Error(http.NOT_FOUND, "Node not found")

        d = self.service.items(jid, nodeIdentifier, maxItems)
        d.addCallback(toResponse)
        d.addErrback(trapNotFound)
        return d



# Client side code to interact with a service as provided above

def getPageWithFactory(url, contextFactory=None, *args, **kwargs):
    """Download a web page.

    Download a page. Return the factory that holds a deferred, which will
    callback with a page (as a string) or errback with a description of the
    error.

    See HTTPClientFactory to see what extra args can be passed.
    """

    factory = client.HTTPClientFactory(url, *args, **kwargs)
    factory.protocol.handleStatus_204 = lambda self: self.handleStatus_200()

    if factory.scheme == 'https':
        from twisted.internet import ssl
        if contextFactory is None:
            contextFactory = ssl.ClientContextFactory()
        reactor.connectSSL(factory.host, factory.port, factory, contextFactory)
    else:
        reactor.connectTCP(factory.host, factory.port, factory)
    return factory



class CallbackResource(resource.Resource):
    """
    Web resource for retrieving gateway notifications.
    """

    def __init__(self, callback):
        self.callback = callback


    http_GET = None


    def render_POST(self, request):
        if request.requestHeaders.hasHeader(b'Event'):
            payload = None
        else:
            payload = parseXml(request.content.read())

        self.callback(payload, request.requestHeaders)

        request.setResponseCode(http.NO_CONTENT)
        return b''




class GatewayClient(service.Service):
    """
    Service that provides client access to the HTTP Gateway into Idavoll.
    """

    agent = "Idavoll HTTP Gateway Client"

    def __init__(self, baseURI, callbackHost=None, callbackPort=None):
        self.baseURI = baseURI
        self.callbackHost = callbackHost or 'localhost'
        self.callbackPort = callbackPort or 8087
        root = resource.Resource()
        root.putChild('callback', CallbackResource(
                lambda *args, **kwargs: self.callback(*args, **kwargs)))
        self.site = server.Site(root)


    def startService(self):
        self.port = reactor.listenTCP(self.callbackPort,
                                      self.site)


    def stopService(self):
        return self.port.stopListening()


    def _makeURI(self, verb, query=None):
        uriComponents = urlparse.urlparse(self.baseURI)
        uri = urlparse.urlunparse((uriComponents[0],
                                   uriComponents[1],
                                   uriComponents[2] + verb,
                                   '',
                                   query and urllib.urlencode(query) or '',
                                   ''))
        return uri


    def callback(self, data, headers):
        pass


    def ping(self):
        f = getPageWithFactory(self._makeURI(''),
                               method='HEAD',
                               agent=self.agent)
        return f.deferred


    def create(self):
        f = getPageWithFactory(self._makeURI('create'),
                    method='POST',
                    agent=self.agent)
        return f.deferred.addCallback(simplejson.loads)


    def delete(self, xmppURI, redirectURI=None):
        query = {'uri': xmppURI}

        if redirectURI:
            params = {'redirect_uri': redirectURI}
            postdata = simplejson.dumps(params)
            headers = {'Content-Type': MIME_JSON}
        else:
            postdata = None
            headers = None

        f = getPageWithFactory(self._makeURI('delete', query),
                    method='POST',
                    postdata=postdata,
                    headers=headers,
                    agent=self.agent)
        return f.deferred


    def publish(self, entry, xmppURI=None):
        query = xmppURI and {'uri': xmppURI}

        f = getPageWithFactory(self._makeURI('publish', query),
                    method='POST',
                    postdata=entry.toXml().encode('utf-8'),
                    headers={'Content-Type': MIME_ATOM_ENTRY},
                    agent=self.agent)
        return f.deferred.addCallback(simplejson.loads)


    def listNodes(self):
        f = getPageWithFactory(self._makeURI('list'),
                    method='GET',
                    agent=self.agent)
        return f.deferred.addCallback(simplejson.loads)


    def subscribe(self, xmppURI):
        params = {'uri': xmppURI,
                  'callback': 'http://%s:%s/callback' % (self.callbackHost,
                                                         self.callbackPort)}
        f = getPageWithFactory(self._makeURI('subscribe'),
                    method='POST',
                    postdata=simplejson.dumps(params),
                    headers={'Content-Type': MIME_JSON},
                    agent=self.agent)
        return f.deferred


    def unsubscribe(self, xmppURI):
        params = {'uri': xmppURI,
                  'callback': 'http://%s:%s/callback' % (self.callbackHost,
                                                         self.callbackPort)}
        f = getPageWithFactory(self._makeURI('unsubscribe'),
                    method='POST',
                    postdata=simplejson.dumps(params),
                    headers={'Content-Type': MIME_JSON},
                    agent=self.agent)
        return f.deferred


    def items(self, xmppURI, maxItems=None):
        query = {'uri': xmppURI}
        if maxItems:
             query['max_items'] = int(maxItems)
        f = getPageWithFactory(self._makeURI('items', query),
                    method='GET',
                    agent=self.agent)
        return f.deferred

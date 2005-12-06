from twisted.words.xish import domish

NS = 'http://jabber.org/protocol/disco'
NS_INFO = NS + '#info'
NS_ITEMS = NS + '#items'

class Feature(domish.Element):
    def __init__(self, feature):
        domish.Element.__init__(self, (NS_INFO, 'feature'),
                                attribs={'var': feature})
class Identity(domish.Element):
    def __init__(self, category, type, name = None):
        domish.Element.__init__(self, (NS_INFO, 'identity'),
                                attribs={'category': category,
                                         'type': type})
        if name:
            self['name'] = name

class Item(domish.Element):
    def __init__(self, jid, node = None, name = None):
        domish.Element.__init__(self, (NS_ITEMS, 'item'),
                                attribs={'jid': jid})
        if node:
            self['node'] = node

        if name:
            self['name'] = name


NS_XMPP_STANZAS = "urn:ietf:params:xml:ns:xmpp-stanzas"

conditions = {
	'bad-request':				{'code': '400', 'type': 'modify'},
	'not-authorized':			{'code': '401', 'type': 'cancel'},
	'item-not-found':			{'code': '404', 'type': 'cancel'},
	'feature-not-implemented':	{'code': '501', 'type': 'cancel'},
}

def error_from_iq(iq, condition, text = '', type = None):
	iq.swapAttributeValues("to", "from")
	iq["type"] = 'error'
	e = iq.addElement("error")

	c = e.addElement((NS_XMPP_STANZAS, condition), NS_XMPP_STANZAS)

	if type == None:
		type = conditions[condition]['type']

	code = conditions[condition]['code']

	e["code"] = code
	e["type"] = type

	if text:
		t = e.addElement((NS_XMPP_STANZAS, "text"), NS_XMPP_STANZAS, text)

	return iq

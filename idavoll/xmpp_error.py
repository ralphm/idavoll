conditions = {
	'not-authorized':			{'code': '401', 'type': 'cancel'},
	'item-not-found':			{'code': '404', 'type': 'cancel'},
	'feature-not-implemented':	{'code': '501', 'type': 'cancel'},
}

def error_from_iq(iq, condition, text = '', type = None):
	iq.swapAttributeValues("to", "from")
	iq["type"] = 'error'
	e = iq.addElement("error")

	c = e.addElement(condition)
	c["xmlns"] = "urn:ietf:params:xml:ns:xmpp-stanzas"

	if type == None:
		type = conditions[condition]['type']

	code = conditions[condition]['code']

	e["code"] = code
	e["type"] = type

	if text:
		t = e.addElement("text", None, text)
		t["xmlns"] = "urn:ietf:params:xml:ns:xmpp-stanzas"

	return iq

from twisted.xish import domish

NS_X_DATA = 'jabber:x:data'

class Field(domish.Element):
    def __init__(self, type="text-single", var=None, label=None):
        domish.Element.__init__(self, (NS_X_DATA, 'field'))
        self["type"] = type
        if var is not None:
            self["var"] = var
        if label is not None:
            self["label"] = label

    def set_value(self, value):
        # TODO: handle *-multi types

        if self["type"] == 'boolean':
            value = str(int(bool(value)))
        else:
            value = str(value)

        try:
            value_element = self.value
            value_element.children = []
        except:
            value_element = self.addElement("value")

        value_element.addContent(value)

class Form(domish.Element):
    def __init__(self, type, form_type):
        domish.Element.__init__(self, (NS_X_DATA, 'x'),
                                attribs={'type': type})
        self.add_field_single(type="hidden", var="FORM_TYPE", value=form_type)

    def add_field_single(self, type="text-single", var=None, label=None,
                         value=None):
        field = Field(type, var, label)
        if value is not None:
            field.set_value(value)
        self.addChild(field)

# Copyright (c) 2003-2006 Ralph Meijer
# See LICENSE for details.

try:
    from twisted.application.service import ServiceMaker
except ImportError:
    from twisted.scripts.mktap import _tapHelper as ServiceMaker

Idavoll = ServiceMaker(
        "Idavoll",
        "idavoll.tap",
        "Jabber Publish-Subscribe Service Component",
        "idavoll")

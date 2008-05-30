# Copyright (c) 2003-2008 Ralph Meijer
# See LICENSE for details.

try:
    from twisted.application.service import ServiceMaker
except ImportError:
    from twisted.scripts.mktap import _tapHelper as ServiceMaker

Idavoll = ServiceMaker(
        "Idavoll HTTP",
        "idavoll.tap_http",
        "Jabber Publish-Subscribe Service Component with HTTP gateway",
        "idavoll-http")

#!/usr/bin/env python3

import logging

#from .msg_bus import (BusNode, BusListener, BusRole, MsgData)
#from ..driver import (PortFunc, io_registry, DriverReadError)


log = logging.getLogger('MiscNodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== miscellaneous ==========

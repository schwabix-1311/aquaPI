#!/usr/bin/env python3

import logging
import sys
from collections import deque
from time import time

from .msg_bus import (BusListener, BusRole, MsgData)
# from ..driver import (PortFunc, io_registry, DriverReadError)


log = logging.getLogger('MiscNodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== miscellaneous ==========


# IDEA: this could use BusRoles to define inputs

class History(BusListener):
    """ A multi-input node, recording all inputs with timestamps.

        Options:
            name       - unique name of this output node in UI
            inputs     - ids of a inputs to be recorded
            length     - max. count of entries  TBD!

        Output:
            - nothing -
    """
    ROLE = BusRole.HISTORY

    def __init__(self, name, inputs, duration=24, _cont=False):
        super().__init__(name, inputs, _cont=_cont)
        self._store = {}
        self.duration = duration
        self.data = 0  # just anything for MsgBorn
        self._nextrefresh = time()

    def __getstate__(self):
        state = super().__getstate__()
        to_dict = {}
        for snd in self._store.copy():
            to_dict[snd] = [(v[0], v[1]) for v in self._store[snd]]
        state.update(store=to_dict)
        return state

    def __setstate__(self, state):
        self.__init__(state['name'], state['inputs'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            now = int(time())
            if msg.sender not in self._store:
                log.debug('%s: new history for %s', self.name, msg.sender)
                self._store[msg.sender] = deque(maxlen=self.duration * 60 * 60)  # limit to 1/sec for one day
            curr = self._store[msg.sender]
            if not curr or (curr[-1][0] != now):  # TODO preliminary: only store 1st value for each second
                curr.append((now, msg.data))
            while curr[0][0] < now - self.duration * 60 * 60:
                curr.popleft()
            log.debug('%s: append %r for %s, %d ent., %d Byte', self.name, msg.data, msg.sender, len(self._store[msg.sender]), sys.getsizeof(self._store[msg.sender]))
            if time() >= self._nextrefresh:
                self.post(MsgData(self.id, 0))
                self._nextrefresh = now + 60

    def get_settings(self):
        return []
##        settings = super().get_settings()
##        settings.append(('duration', 'max. Dauer', self.duration,
##                         'type="number" min="0" max="%d"' % (24*60*60)))
##        return settings

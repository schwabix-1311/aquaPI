#!/usr/bin/env python3

import logging
import sys
import os
from collections import deque
from time import time

from .msg_bus import (BusListener, BusRole, MsgData)
# from ..driver import (PortFunc, io_registry, DriverReadError)


log = logging.getLogger('MiscNodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== preliminary interface to InfluxDB ==========

INFLUX_SRV = 'localhost'    # can be an IP
INFLUX_PORT = 8086
INFLUX_URL = f'http://{INFLUX_SRV}:{INFLUX_PORT}'

def _curl_http(method, endpoint, data=None, option=None):
    cmd = f'curl -i -{method} "{INFLUX_URL}/{endpoint}"'
    if option:
        cmd = f'curl -i -{method} "{INFLUX_URL}/{endpoint}?{option}"'
    if data:
        cmd += ' ' + data
    os.system(cmd)

def _curl_query(flux, option=None):
    _curl_http('GET', 'query', data=f'--data-urlencode "q={flux}"', option=option)

def _curl_post(flux, option=None):
    _curl_http('XPOST', 'query', data=f'--data-urlencode "q={flux}"', option=option)

def _curl_write(line, option=None):
    _curl_http('XPOST', 'write', data=f'--data-binary "{line}"', option=option)


def create_influx(db_name, node_id):
    cmds = [f'CREATE DATABASE {db_name} WITH DURATION 1h'
           ,f'CREATE RETENTION POLICY one_day ON {db_name} DURATION 1d REPLICATION 1'
           ,f'CREATE RETENTION POLICY one_month ON {db_name} DURATION 31d REPLICATION 1'
           ,f'CREATE CONTINUOUS QUERY qc_day_{node_id} ON {db_name} BEGIN' \
             '  SELECT mean(*) INTO {db_name}.one_day.:MEASUREMENT'\
             '  FROM {db_name}.autogen.{node_id} GROUP BY time(1m),*'\
             'END'
           # ,'CREATE CONTINUOUS QUERY qc_month_rp ON %s BEGIN SELECT mean(*),median(*) INTO %s.one_month.:MEASUREMENT FROM %s.one_day./.*/ GROUP BY time(1h),* END' % (db_name, db_name, db_name))
           ]
    if INFLUX_SRV == 'localhost':
        os.system('influx -execute "' + '; '.join(cmds) + '"')
    else:
        for cmd in cmds:
            _curl_post(cmd)

def feed_influx(db_name, node_id, value):
    data = f'{node_id} {value[0]}={value[1]}'

    # shortcut for localhost, could be extended for post/query
    if INFLUX_SRV == 'localhost':
        os.system(f'influx -database={db_name} -precision=s  -execute "INSERT {data}"')
    else:
        _curl_write(data, option=f'db={db_name}&precision=s')


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

        create_influx('aquaPi', self.id)

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

            feed_influx('aquaPi', self.id, (msg.sender, msg.data))

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

    def get_history(self, start, step):
        h = influx_query('aquaPi',
                         'select time, %s from %s where time > %d'
                         % (','.join(self._inputs.sender), self.id, start))
        hist = []
        return hist

    def get_settings(self):
        return []
##        settings = super().get_settings()
##        settings.append(('duration', 'max. Dauer', self.duration,
##                         'type="number" min="0" max="%d"' % (24*60*60)))
##        return settings

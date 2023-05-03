#!/usr/bin/env python3

import logging
import sys
from shutil import which
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

INFLUX_CMD = 'influx'
INFLUX_SRV = 'localhost'    # can be None for simulation, or an IP
INFLUX_PORT = 8086
INFLUX_URL = f'http://{INFLUX_SRV}:{INFLUX_PORT}'

# if no Influx tool exists for localhost, simulate the DB,
# but if you specify an IP, this must be a valid instance
if INFLUX_SRV == "localhost" and not which(INFLUX_CMD):
    INFLUX_SRV = None


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
# with QuestDB, following downsample produces sensible data:
# SELECT span,id,avg(value) from(
#   SELECT ts span,n.node_id id,avg(value) value FROM value JOIN node n ON (node_id) SAMPLE BY 1s FILL (PREV)
# )
#   --where ts between '2023-04-29T09:00:00Z' and  '2023-04-29T09:30:00Z'
#   --where id='ph'
#  sample by 8h fill (prev) align to CALENDAR group by span, id;

# bug / unexpected behaviour:
# none of downsampling methods fills gaps in sparse data reliably, may even drop measurements completely if no value inside queried interval!
    cmds = [f'CREATE DATABASE {db_name} WITH DURATION 1h'
           ,f'CREATE RETENTION POLICY one_day ON {db_name} DURATION 1d REPLICATION 1'
           ,f'CREATE RETENTION POLICY one_month ON {db_name} DURATION 31d REPLICATION 1'
           ,f'CREATE CONTINUOUS QUERY qc_day_{node_id} ON {db_name} BEGIN' \
             '  SELECT mean(*)'\
             '    RESAMPLE EVERY 1m'\
             '    INTO {db_name}.one_day.:MEASUREMENT'\
             '    FROM ('\
             '      SELECT mean(*) FROM {db_name}.autogen.{node_id} GROUP BY time(1s),* FILL(previous)'\
             '    )'\
             '    GROUP BY time(1m),*'\
             'END'
           ,f'CREATE CONTINUOUS QUERY qc_month_{node_id} ON {db_name} BEGIN' \
             '  SELECT mean(*)'\
             '    RESAMPLE EVERY 1h'\
             '    INTO {db_name}.one_month.:MEASUREMENT'\
             '    FROM ('\
             '      SELECT mean(*) FROM {db_name}.autogen.{node_id} GROUP BY time(1s),* FILL(previous)'\
             '    )'\
             '    GROUP BY time(1h),*'\
             'END'
           # ,'CREATE CONTINUOUS QUERY qc_month_rp ON %s BEGIN SELECT mean(*),median(*) INTO %s.one_month.:MEASUREMENT FROM %s.one_day./.*/ GROUP BY time(1h),* END' % (db_name, db_name, db_name))
           ]
    if not INFLUX_SRV:
        pass
    elif INFLUX_SRV == 'localhost':
        os.system('influx -execute "' + '; '.join(cmds) + '"')
    else:
        for cmd in cmds:
            _curl_post(cmd)

def feed_influx(db_name, node_id, value):
# with QuestDB, this would work, although Influx LineProtocol is recommended (perf!):
# curl -G --data-urlencode "query=INSERT INTO value VALUES(now(),'phsensor', 2.48),(now(),'phcalibration',6.47)" http://localhost:9000/exec
    data = f'{node_id} {value[0]}={value[1]}'

    # shortcut for localhost, could be extended for post/query
    if not INFLUX_SRV:
        pass
    elif INFLUX_SRV == 'localhost':
        os.system(f'influx -database={db_name} -precision=s -execute "INSERT {data}"')
    else:
        _curl_write(data, option=f'db={db_name}&precision=s')

def query_influx(db_name, flux):
    breakpoint()
    if not INFLUX_SRV:
        pass
    elif INFLUX_SRV == 'localhost':
        os.system(f'influx -database={db_name} -precision=s -execute "{flux}"')
    else:
        _curl_query(flux, option="db={db_name}&precision=s")
    return []


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
        h = query_influx('aquaPi',
                         f'SELECT time, * FROM {self.id} WHERE time > {start}'
                         #'SELECT time, mean(*) FROM {self.id} WHERE time > {start}'
                         #% (','.join(self._inputs.sender), self.id, start))
                        )
        hist = []
        return hist

    def get_settings(self):
        return []
##        settings = super().get_settings()
##        settings.append(('duration', 'max. Dauer', self.duration,
##                         'type="number" min="0" max="%d"' % (24*60*60)))
##        return settings

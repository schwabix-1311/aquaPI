#!/usr/bin/env python3

from abc import ABC, abstractmethod
import logging
import sys
import platform
from collections import deque
from time import time

from .msg_bus import (BusListener, BusRole, MsgData)
# from ..driver import (PortFunc, io_registry, DriverReadError)


log = logging.getLogger('MiscNodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== interface to time series DB ==========


class TimeDb(ABC):
    """ Base class for time series storage
    """
    fields = []

<<<<<<< HEAD
    def __init__(self):
=======
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
>>>>>>> 7f00786 (The downsampling query tested during evaluation)
        pass

<<<<<<< HEAD
    def add_field(self, name):
        if name not in TimeDb.fields:
            TimeDb.fields.append(name)
=======
def feed_influx(db_name, node_id, value):
# with QuestDB, this would work, although Influx LineProtocol is recommended (perf!):
# curl -G --data-urlencode "query=INSERT INTO value VALUES(now(),'phsensor', 2.48),(now(),'phcalibration',6.47)" http://localhost:9000/exec
    data = f'{node_id} {value[0]}={value[1]}'
>>>>>>> 7f00786 (The downsampling query tested during evaluation)

    @abstractmethod
    def feed(self, name, value):
        pass

    @abstractmethod
    def query(self, fieldnames, start=0, step=0):
        pass


class TimeDbMemory(TimeDb):
    """ Time series storage using main memory
        No persistance yet!
    """
    _store = {}  # one storage shared by all HistoryNodes

    def __init__(self, duration):
        """ in-memory storage is limited to {duration} hours
        """
        super().__init__()
        self.duration = duration

    def add_field(self, name):
        super().add_field(name)
        if name not in TimeDbMemory._store:
            log.debug('TimeDbMemory: new history for %s', name)
            TimeDbMemory._store[name] = deque(maxlen=self.duration * 60 * 60)  # 1/sec

    def feed(self, name, value):
        now = int(time())
        series = TimeDbMemory._store[name]
        if not series or (series[-1][0] != now):
            series.append((now, value))
        else:
            series[-1] = (now, (series[-1][1] + value) / 2)

        # purge expired data
        while series[0][0] < now - self.duration * 60 * 60:
            series.popleft()
        log.debug('TimeDbMemory: append %s: %r @ %d, %d ent., %d Byte'
                 , name, value, now
                 , len(TimeDbMemory._store[name])
                 , sys.getsizeof(TimeDbMemory._store[name]))

#TODO: once transistion is finished, TimeDbMemory._store can change to new structure
#TODO: add downsampling of returned data if step>1
#TODO: add permanent downsampling after some period, e.g. 1h, to reduce mem consumption
    def query(self, fieldnames, start=0, step=0):
        store_cpy = TimeDbMemory._store.copy()  # freeze the source, could lock it instead
        result = {}

        if not start and not step:
            # just for reference, was never used with this API!
            # previous struct:
            #   {ser1: [(ts1, val1.1), (ts2, val1.2), ...],
            #    ser2: [(ts1, val2.1), (ts2, val2.2),....],
            #    ... }
            for name in fieldnames:
                result[name] = [(v[0], v[1]) for v in store_cpy[name]]
        else:
            # new structure, about 0.7 * space:
            #   { 0:  ["ser1", "ser2", ...],
            #    ts1: [val1.1, val2.1, ...],
            #    ts2: [val1.2, val2.2, ...],
            #    ... }
            # each val may be null!
            result[0] = fieldnames
            empty = [None] * len(fieldnames)
            idx = 0
            for name in fieldnames:
                # make sure there is a tupel for start time
                if not start in result:
                    result[start] = empty
                for measurement in store_cpy[name]:
                    (ts, val) = measurement
                    if ts <= start:
                        # still <= start, so update
                        result[start][idx] = val
                    else:
                        # past start, ensure a tupel for ts exists
                        if not ts in result:
                            result[ts] = empty
                        result[ts][idx] = val
                idx += 1

        return result


class TimeDbQuest(TimeDb):
    """ Time series storage using QuestDB
        QuestDB does not support ARM32/armlf, which excludes
        Raspberry 1/2/zero completely, and later models if
        they use the common 32bit editions of Raspbian or Raspberry OS
    """
    def __init__(self):
        if '32' in platform.architecture()[0]:
            raise NotImplementedError()
        #TODO if not exist QuestDB: raise ModuleNotFoundError
        #    raise ModuleNotFoundError()

        super().__init__()
        self.db_name = 'aquaPi'

        raise NotImplementedError()

    def feed(self, name, value):
        raise NotImplementedError()

    def query(self, fieldnames, start=0, step=0):
        raise NotImplementedError()


# ========== miscellaneous ==========


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
        self.duration = duration
        self.data = 0  # just anything for MsgBorn
        self._nextrefresh = time()
        try:
            self.db = TimeDbQuest()
            log.brief('Recording history in QuestDB')
        except (NotImplementedError, ModuleNotFoundError):
            self.db = TimeDbMemory(duration)
            log.brief('Recording history in main memory with limited depth of %dh!', duration)
        for snd in self._inputs.sender:
            self.db.add_field(snd)

    def __getstate__(self):
        state = super().__getstate__()
        hist = self.db.query(self._inputs.sender)
        state.update(store=hist)            #TODO remove -> History API!
        return state

    def __setstate__(self, state):
        self.__init__(state['name'], state['inputs'], _cont=True)

    def listen(self, msg):
        if isinstance(msg, MsgData):
            self.db.feed(msg.sender, msg.data)
            if time() >= self._nextrefresh:
                self.post(MsgData(self.id, 0))
                self._nextrefresh = int(time()) + 60

    def get_history(self, start, step):
        return self.db.query(self._inputs.sender, start, step)

    def get_history(self, start, step):
        hist = []
        return hist

    def get_settings(self):
        return []
##        settings = super().get_settings()
##        settings.append(('duration', 'max. Dauer', self.duration,
##                         'type="number" min="0" max="%d"' % (24*60*60)))
##        return settings

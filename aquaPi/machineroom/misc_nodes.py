#!/usr/bin/env python3

from abc import ABC, abstractmethod
import logging
import os
import sys
import platform
import regex
from collections import deque
from time import time
try:
    import psycopg as pg
    from psycopg import sql
    QUEST_DB = True
except:
    QUEST_DB = False

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

    def __init__(self):
        pass

    def add_field(self, name):
        if name not in TimeDb.fields:
            TimeDb.fields.append(name)

    @abstractmethod
    def feed(self, name, value):
        pass

    @abstractmethod
    def query(self, node_names, start=0, step=0):
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
    def query(self, node_names, start=0, step=0):
        store_cpy = TimeDbMemory._store.copy()  # freeze the source, could lock it instead
        result = {}

        if not start and not step:
            # just for reference, was never used with this API!
            # previous struct:
            #   {ser1: [(ts1, val1.1), (ts2, val1.2), ...],
            #    ser2: [(ts1, val2.1), (ts2, val2.2),....],
            #    ... }
            for name in node_names:
                result[name] = [(v[0], v[1]) for v in store_cpy[name]]
        else:
            # new structure, about 0.7 * space:
            #   { 0:  ["ser1", "ser2", ...],
            #    ts1: [val1.1, val2.1, ...],
            #    ts2: [val1.2, val2.2, ...],
            #    ... }
            # each val may be null!
            result[0] = node_names
            result[start] = [None] * len(node_names)
            idx = 0
            for name in node_names:
                for measurement in store_cpy[name]:
                    (ts, val) = measurement
                    if ts <= start:
                        # still <= start, so update
                        result[start][idx] = val
                    else:
                        # past start, ensure a tupel for ts exists
                        if not ts in result:
                            result[ts] = [None] * len(node_names)
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
        # likewise in shell: getconf LONG_BIT
        if '32' in platform.architecture()[0]:
            raise NotImplementedError()
        #TODO if not exist QuestDB: raise ModuleNotFoundError
        #    raise ModuleNotFoundError()

        super().__init__()
        try:
            self.conn_str = 'host=localhost port=8812 ' \
                          + 'user=admin password=quest ' \
                          + 'dbname=aquaPi application_name=aquaPi'
            self.timezone = self._get_local_tz()
# pylint: disable-next: E1129
            conn = pg.connect(self.conn_str, autocommit=True)
            with conn:
                conn.execute("SET TIME ZONE %s", [self.timezone])
                conn.execute("""
                  CREATE TABLE IF NOT EXISTS node
                    ( node_id symbol CAPACITY 64 INDEX,
                      linear_fill boolean );
                  CREATE TABLE IF NOT EXISTS value
                    ( ts timestamp,
                      node_id symbol CAPACITY 64,
                      value double )
                    timestamp(ts) PARTITION BY HOUR;
                  """)
            conn.close()
        except pg.OperationalError as ex:
            log.warning('TimeQuestDB - %s', str(ex))
            raise ModuleNotFoundError() from ex

    @staticmethod
    def _get_local_tz():
        # time is a bad concept, troublesome everywhere!
        #FIXME: this sets QuestDB to local timezone. Sensible for aquaPi host and the DB, which means debugging and logs. Conversion to and from user's TZ must be done in frontend!

        # To make things interesting, there's no simple way to get the 'Olson TZ name' (e.g. 'Europe/Belin'), most systems prefer the 3-4 letter names, e.g. CEST. Reading link /etc/localtime has several chances to break, but seems to work on Raspi (and Manjaro).
        tzfile = os.readlink('/etc/localtime')
        match = regex.search('/zoneinfo/(.*)$', tzfile)
        if not match:
            return 'UTC'
        return match[1]

    def add_field(self, name):
        super().add_field(name)
        try:
            conn = pg.connect(self.conn_str, autocommit=True)
            with conn:
                with conn.cursor() as curs:
                    qry = sql.SQL("SELECT {node_id} FROM node WHERE {node_id}=%s").format(
                            node_id=sql.Identifier('node_id'))
                    curs.execute(qry, [name])
                    rec = curs.fetchone()
                    if not rec:
                        qry = sql.SQL("INSERT INTO node VALUES (%s, true)")
                        conn.execute(qry, [name])
            conn.close()
        except pg.OperationalError as ex:
            log.warning('TimQuestDB.add_field - %s', str(ex))

    def feed(self, name, value):
        try:
            conn = pg.connect(self.conn_str, autocommit=True)
            with conn:
                qry = sql.SQL("INSERT INTO value VALUES (now(), %s, %s)")
                conn.execute(qry, [name, value])
            conn.close()
        except pg.OperationalError as ex:
            log.warning('TimeQuestDB.feed - %s', str(ex))

    def _query(self, node_names, start, step):
        try:
            conn = None
            if start <= 0:
                start = int(time()) - 24 * 60 * 60  # default to now-24h

            conn = with pg.connect(self.conn_str, autocommit=True)
            with conn:
                with conn.cursor() as curs:
                    if step <= 0:
                        # unsampled = raw data
                        qry =  sql.SQL("""
                          SELECT to_timezone(ts,{timezone}) ts, node_id, value
                            FROM value -- JOIN node ON (node_id)
                            WHERE ts >= to_utc({start} * 1000000L, {timezone})
                              AND node_id IN ({nodes})
                            ORDER BY ts,node_id;
                          """).format(
                        timezone=sql.Literal(self.timezone),
                        start=sql.Literal(start),
                        nodes=sql.SQL(',').join(node_names)
                      )
                    else:
                        qry =  sql.SQL("""
                          SELECT to_timezone(ts,{timezone}) span, id, avg(value) FROM (
                            SELECT ts, node_id id, avg(value) value
                              FROM value -- JOIN node ON (node_id)
                              WHERE ts >= to_utc({start} * 1000000L, {timezone})
                              SAMPLE BY 1s FILL (PREV)
                            )
                            WHERE id IN ({nodes})
                            SAMPLE BY {step}s FILL (PREV) ALIGN TO CALENDAR
                            GROUP BY ts,id ORDER BY span,id;
                          """).format(
                            timezone=sql.Literal(self.timezone),
                            start=sql.Literal(start),
                            step=sql.Literal(step),
                            nodes=sql.SQL(',').join(node_names)
                          )
                    log.debug(qry.as_string(conn))
                    curs.execute(qry)
                    recs = curs.fetchall()

                    return recs
        finally:
            if conn:
                conn.close()

        except pg.OperationalError as ex:
            log.warning('TimeQuestDB.query - %s', str(ex))
            return {}

    def query(self, node_names, start=0, step=0):
        result = {}

        qry_begin = time()
        log.debug('TimeDbQuest query: %s / %d / %d', node_names, start, step)
        recs = self._query(node_names, start, step)
        log.debug('  qry time %fs', time() - qry_begin)

        if recs:
            #for row in recs:
            #    log.debug(row)

            if start <= 0:
                # old structure (start=0), each series is an array of data point tupels:
                # { "ser1": [(ts1, val1.1), (ts2: val1.2), ... ],
                #   "ser2": [(ts1, val2.1), (ts3, val2.3), ... ],
                #    ... }
                for node in node_names:
                    result[node] = [(r[0].timestamp(),r[2]) for r in recs if r[1]==node]

            else:
                # new structure, typically about 30% less space:
                #   { 0:  ["ser1", "ser2", ...],
                #    ts1: [val1.1, val2.1, ...],
                #    ts2: [val1.2, None,   ...],
                #    ts3: [None,   val2.3, ...],
                #    ... }
                # each val may be null!
                result = {}
                result[0] = node_names
                result[start] = [None] * len(node_names)
                for row in recs:
                    (dt_tm, node, val) = row
                    ts = int(dt_tm.timestamp())  # max resolution is 1sec
                    n_idx = node_names.index(node)
                    if ts <= start:
                        # still <= start, so update
                        result[start][n_idx] = val
                    else:
                        # past start, ensure a tupel for ts exists
                        if not ts in result:
                            result[ts] = [None] * len(node_names)
                        result[ts][n_idx] = val

                # null out the unchanged values,
                # this safes processing time for rare events in chart
                prev = result[start].copy()
                for ts in result.keys():
                    if ts <= start:
                        continue
                    for node in node_names:
                        n_idx = node_names.index(node)
                        if prev[n_idx] is None:
                            prev[n_idx] = result[ts][n_idx]
                        elif result[ts][n_idx] == prev[n_idx]:
                            result[ts][n_idx] = None
                        elif result[ts][n_idx] is not None:
                            prev[n_idx] = result[ts][n_idx]
                result = {ts: result[ts] for ts in result if result[ts] != [None] * len(node_names)}

        log.debug('  done, overall %fs', time() - qry_begin)
        return result


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
        except (NotImplementedError, ModuleNotFoundError, ImportError):
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

    def get_settings(self):
        return []
##        settings = super().get_settings()
##        settings.append(('duration', 'max. Dauer', self.duration,
##                         'type="number" min="0" max="%d"' % (24*60*60)))
##        return settings

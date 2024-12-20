#!/usr/bin/env python3

from abc import (ABC, abstractmethod)
import logging
from typing import (Any, Iterable)
import os
import sys
import platform
import regex
from collections import deque
from time import time
from datetime import datetime
from threading import Lock

try:
    import psycopg as pg
    from psycopg.sql import (SQL, Identifier, Literal)
    QUEST_DB = True
except Exception:
    QUEST_DB = False

from .msg_bus import (BusListener, BusRole, MsgData)


log = logging.getLogger('machineroom.hist_nodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== interface to time series DB ==========


class TimeDb(ABC):
    """ Base class for time series storage
    """
    fields: set[str] = set()

    ValueLst = list[str | float | None]

    def __init__(self):
        pass

    def add_field(self, name: str) -> None:
        TimeDb.fields.add(name)

    @abstractmethod
    def feed(self, name: str, value: int | float) -> None:
        pass

    @abstractmethod
    def query(self, node_names: Iterable[str], start: int = 0, step:  int = 0
              # ) -> dict[int, list[str | float]]:
              ) -> dict[int, ValueLst]:
        pass


class TimeDbMemory(TimeDb):
    """ Time series storage using main memory
        No persistance yet!
    """
    # one storage shared by all HistoryNodes
    _store: dict[str, deque[tuple[int, int | float]]] = dict()
    _store_lock = Lock()

    def __init__(self, duration: int):
        """ in-memory storage is limited to {duration} hours
        """
        super().__init__()
        self.duration = duration

    def add_field(self, name: str) -> None:
        super().add_field(name)
        TimeDbMemory._store.setdefault(name, deque(maxlen=self.duration * 60 * 60))  # 1/sec

    def feed(self, name: str, value: int | float) -> None:
        with TimeDbMemory._store_lock:
            TimeDbMemory._store.setdefault(name, deque(maxlen=self.duration * 60 * 60))  # 1/sec

            now = int(time())
            series = TimeDbMemory._store[name]
            if (len(series) == 0 or series[-1][0] != now):
                series.append((now, value))
            else:
                # multiple values for same second, build average
                series[-1] = (now, (series[-1][1] + value) / 2)

            # purge expired data
            while series[0][0] < now - self.duration * 60 * 60:
                series.popleft()

            log.debug('TimeDbMemory: append %s: %r @ %d, %d ent., %d Byte',
                      name, value, now,
                      len(TimeDbMemory._store[name]),
                      sys.getsizeof(TimeDbMemory._store[name]))

#TODO: add downsampling of returned data if step>1
#TODO: add permanent downsampling after some period, e.g. 1h, to reduce mem consumption

    def query(self, node_names: Iterable[str],
              start: int = 1, step: int = 0
              # ) -> dict[int, list[str | float | None]]:
              ) -> dict[int, TimeDb.ValueLst]:
        with TimeDbMemory._store_lock:

            qry_begin = time()

            # new structure, about 0.7 * space:
            #   { 0:  ["ser1", "ser2", ...],
            #    ts1: [val1.1, val2.1, ...],
            #    ts2: [val1.2, val2.2, ...],
            #    ... }
            # each val may be null!
            # result: dict[int, list[str | float | None]] = dict()
            result: dict[int, TimeDb.ValueLst] = dict()
            result[0] = [nm for nm in node_names]

            start = max(1, start)
            result[start] = TimeDb.ValueLst = [None] * len(result[0])
            for idx, name in enumerate(node_names):
                series = TimeDbMemory._store[name]
                for measurement in series:
                    (ts, val) = measurement
                    if ts <= start:
                        # still <= start, so update
                        result[start][idx] = val
                    else:
                        # past start, ensure a tupel for ts exists
                        if ts not in result:
                            result[ts] = TimeDb.ValueLst = [None] * len(result[0])
                        result[ts][idx] = val

            log.debug('TimeDbMemory.query %r start %r step %r', node_names, start, step)
            log.debug('  done, overall %fs, %d data points', time() - qry_begin, len(result))
            # log.debug('  : %r', result)
            return result


if QUEST_DB:
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

# pylint: disable-next=E1129
                with pg.connect(self.conn_str, autocommit=True) as conn:
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
            except pg.OperationalError as ex:
                if log.level == logging.DEBUG:
                    log.exception('FYI: TimeDbQuest failure')
                raise ModuleNotFoundError() from ex

        @staticmethod
        def _get_local_tz() -> str:
            # time is a bad concept, troublesome everywhere!
            #FIXME: this sets QuestDB to host's local timezone. Ok for debugging and logs. Conversion to and from user's TZ must be done in frontend!
            # To make things interesting, there's no simple way to get the
            # 'Olson TZ name' (e.g. 'Europe/Belin'), most systems prefer the
            # 3-4 letter names, e.g. CEST. Reading link /etc/localtime has
            # several chances to break, but workon Raspi (and Manjaro).
            tzfile = os.readlink('/etc/localtime')
            match = regex.search('/zoneinfo/(.*)$', tzfile)
            if not match:
                return 'UTC'
            return match[1]

        def add_field(self, name: str) -> None:
            super().add_field(name)
            try:
                # pylint: disable-next=E1129
                with pg.connect(self.conn_str, autocommit=True) as conn:
                    with conn.cursor() as curs:
                        qry = SQL("SELECT node_id FROM {} WHERE node_id=%s;"
                                  ).format(Identifier('node'))
                        curs.execute(qry, [name])
                        rec = curs.fetchone()
                        if not rec:
                            qry = SQL("INSERT INTO {} VALUES (%s, true)"
                                      ).format(Identifier('node'))
                            conn.execute(qry, [name])
            except pg.OperationalError:
                log.exception('TimeDbQuest.add_field')

        def feed(self, name: str, value: int | float) -> None:
            try:
                # pylint: disable-next=E1129
                with pg.connect(self.conn_str, autocommit=True) as conn:
                    qry = SQL("INSERT INTO {} VALUES (now(), %s, %s)"
                              ).format(Identifier('value'))
                    conn.execute(qry, [name, value])
            except pg.OperationalError:
                log.exception('TimeDbQuest.feed')

        def _query(self, node_names: Iterable[str],
                   start: int = 0, step: int = 0
                   ) -> list[tuple[datetime, str, float]]:
            try:
                if start <= 0:
                    start = int(time()) - 24 * 60 * 60  # default to now-24h

# pylint: disable-next=E1129
                with pg.connect(self.conn_str, autocommit=True) as conn:
                    with conn.cursor() as curs:
                        q_names = SQL(',').join(map(Literal, node_names))
                        if step <= 0:
                            # unsampled = raw data
                            qry = SQL("""
                              SELECT to_timezone(ts,{tz}) ts, node_id, value
                                FROM value -- JOIN node ON (node_id)
                                WHERE ts >= to_utc({start} * 1000000L, {tz})
                                  AND node_id IN ({nodes})
                                ORDER BY ts,node_id;
                              """).format(tz=Literal(self.timezone),
                                          start=Literal(start),
                                          nodes=q_names)
                        else:
                            qry = SQL("""
                              SELECT to_timezone(ts,{tz}) span, id, avg(value)
                                FROM (
                                  SELECT ts, node_id id, avg(value) value
                                    FROM value -- JOIN node ON (node_id)
                                    WHERE ts >= to_utc({start} *1000000L, {tz})
                                      AND node_id IN ({nodes})
                                    SAMPLE BY 1s FILL (PREV)
                                )
                                --WHERE id IN ({nodes})
                                SAMPLE BY {step}s FILL (PREV) ALIGN TO CALENDAR
                                GROUP BY ts,id ORDER BY span,id;
                              """).format(tz=Literal(self.timezone),
                                          start=Literal(start),
                                          step=Literal(step),
                                          nodes=q_names)
                        #log.debug(qry.as_string(conn))
                        curs.execute(qry)
                        recs = curs.fetchall()

                        return recs
            except pg.OperationalError:
                log.exception('TimeDbQuest.query')
                return []

        def query(self, node_names: Iterable[str],
                  start: int = 1, step:  int = 0
                  ) -> dict[int, TimeDb.ValueLst]:
            names: TimeDb.ValueLst = [n for n in node_names]  # make indexable

            qry_begin = time()
            log.debug('TimeDbQuest qry: %s start %d  step %d', names, start, step)
            recs = self._query(node_names, start, step)
            log.debug('  qry time %fs', time() - qry_begin)

            # new structure, typically about 30% less space:
            #   { 0:  ["ser1", "ser2", ...],
            #    ts1: [val1.1, val2.1, ...],
            #    ts2: [val1.2, None,   ...],
            #    ts3: [None,   val2.3, ...],
            #    ... }
            # each val may be null!
            result: dict[int, TimeDb.ValueLst] = {}
            result[0] = names
# FIXME: refactor!!
            result[start] = TimeDb.ValueLst = [None] * len(result[0])
            for row in recs:
                (dt_tm, node, val) = row
                ts = int(dt_tm.timestamp())  # max resolution is 1sec
                idx = names.index(node)
                if ts <= start:
                    # still <= start, so update
                    result[start][idx] = val
                else:
                    # past start, ensure a tupel for ts exists
                    if ts not in result:
                        result[ts] = TimeDb.ValueLst = [None] * len(result[0])
                    result[ts][idx] = val

            # null out the unchanged values,
            # this safes processing time for rare events in chart
            prev = result[start].copy()
            for ts in result.keys():
                if ts <= start:
                    continue
                for idx, _ in enumerate(node_names):
                    if prev[idx] is None:
                        prev[idx] = result[ts][idx]
                    elif result[ts][idx] == prev[idx]:
                        result[ts][idx] = None
                    elif result[ts][idx] is not None:
                        prev[idx] = result[ts][idx]
            result = {ts: result[ts] for ts in result if result[ts] != [None] * len(names)}

            log.debug('  done, overall %fs, %d data points', time() - qry_begin, len(result))
            # log.debug('  : %r', result)
            return result
# end: if QUEST_DB


# ========== history for charts and statistics ==========


class History(BusListener):
    """ A multi-input node, recording all inputs with timestamps.

        Options:
            name      - unique name of this output node in UI
            receives  - ids of a inputs to be recorded
            length    - max. count of entries  TBD!

        Output:
            - nothing -
    """
    ROLE = BusRole.HISTORY

    def __init__(self, name: str, receives: Iterable[str],
                 duration: int = 24, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.duration = duration
        self.data: int = 0  # just anything for MsgBorn
        self._nextrefresh = time()
        self.db: TimeDb | None = None
        if QUEST_DB:
            try:
                self.db = TimeDbQuest()
                log.brief('Recording history %s in QuestDB', name)
            except (NotImplementedError, ModuleNotFoundError, ImportError):
                log.error('QuestDB failed, will keep history in memory')
        if not self.db:
            self.db = TimeDbMemory(duration)
            log.brief('Recording history %s in main memory with limited depth of %dh!', name, duration)
        for rcv in self.receives:
            self.db.add_field(rcv)

    # def __getstate__(self) -> dict[str, Any]:
    #    state = super().__getstate__()
    #    return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        History.__init__(self, state['name'], state['receives'], _cont=True)

    def listen(self, msg) -> bool:
        if isinstance(msg, MsgData):
            if self.db:
                self.db.feed(msg.sender, msg.data)
            if time() >= self._nextrefresh:
                self.post(MsgData(self.id, 0))
                self._nextrefresh = int(time()) + 10
        return super().listen(msg)

    def get_history(self, start: int, step: int
                    ) -> dict[int, TimeDb.ValueLst]:
        return self.db.query(self.receives, start, step) if self.db else dict()

    def get_settings(self) -> list[tuple]:
        return []
##        settings = super().get_settings()
##        settings.append(('duration', 'max. Dauer', self.duration,
##                         'type="number" min="0" max="%d"' % (24*60*60)))
##        return settings

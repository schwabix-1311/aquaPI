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

from .msg_bus import (BusListener, BusRole, MsgData, Setting)


log = logging.getLogger('machineroom.hist_nodes')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== interface to time series DB ==========


def check_questdb_reachable(timeout: float = 1.0) -> bool:
    """ lightweight, side-effect-free reachability check for QuestDB
        (Step 25 /api/health): tries a short-timeout connection and a
        trivial query, without creating/touching any tables - unlike
        TimeDbQuest.__init__(), which is only used once a History node
        is actually instantiated. Returns False immediately if the
        'psycopg' driver isn't even installed (QUEST_DB == False).
    """
    if not QUEST_DB:
        return False
    try:
        conn_str = ('host=localhost port=8812 user=admin password=quest '
                    'dbname=aquaPi application_name=aquaPi connect_timeout=%d'
                    % max(1, int(timeout)))
        with pg.connect(conn_str, autocommit=True) as conn:
            conn.execute('SELECT 1')
        return True
    except Exception:
        return False


def _questdb_conn_str() -> str:
    return ('host=localhost port=8812 user=admin password=quest '
            'dbname=aquaPi application_name=aquaPi')


def log_calibration_event(node_id: str, field: str,
                          old_value: float, new_value: float) -> bool:
    """ record a calibration change (e.g. a ScaleAux node's 'offset'/
        'factor', typically adjusted after re-calibrating a pH probe or
        similar sensor) with timestamp and old/new value in QuestDB, so
        it can be reviewed later (Step 28). Like the rest of this module,
        this degrades gracefully: if QuestDB isn't installed/reachable,
        the event is just logged and skipped, never raises.
    """
    if not QUEST_DB:
        log.warning('Calibration event for %s.%s not recorded: QuestDB not available',
                    node_id, field)
        return False
    try:
        with pg.connect(_questdb_conn_str(), autocommit=True) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS calibration_log (
                    ts        timestamp,
                    node_id   symbol CAPACITY 64,
                    field     symbol CAPACITY 16,
                    old_value double,
                    new_value double )
                    timestamp(ts) PARTITION BY MONTH;
            """)
            qry = SQL("INSERT INTO {} VALUES (now(), %s, %s, %s, %s)"
                      ).format(Identifier('calibration_log'))
            conn.execute(qry, [node_id, field, old_value, new_value])
        log.brief('Calibration event recorded: %s.%s %s -> %s', node_id, field, old_value, new_value)
        return True
    except Exception:
        log.exception('Failed to record calibration event for %s.%s', node_id, field)
        return False


def get_calibration_log(node_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """ return the most recent calibration events for one node, newest
        first; empty list if QuestDB is unavailable or on any error
    """
    if not QUEST_DB:
        return []
    try:
        with pg.connect(_questdb_conn_str(), autocommit=True) as conn:
            with conn.cursor() as curs:
                qry = SQL("SELECT ts, field, old_value, new_value FROM {} "
                          "WHERE node_id=%s ORDER BY ts DESC LIMIT %s"
                          ).format(Identifier('calibration_log'))
                curs.execute(qry, [node_id, limit])
                rows = curs.fetchall()
                return [{'ts': ts.isoformat(), 'field': field,
                        'old_value': old_value, 'new_value': new_value}
                       for (ts, field, old_value, new_value) in rows]
    except Exception:
        log.exception('Failed to read calibration log for %s', node_id)
        return []


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
        self.data: int = 0  # just anything for MsgHello
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

    def listen(self, msg) -> None:
        if isinstance(msg, MsgData):
            if self.db:
                self.db.feed(msg.sender, msg.data)
            if time() >= self._nextrefresh:
                self.post(MsgData(self.id, 0))
                self._nextrefresh = int(time()) + 10

        super().listen(msg)

    def get_history(self, start: int, step: int
                    ) -> dict[int, TimeDb.ValueLst]:
        return self.db.query(self.receives, start, step) if self.db else dict()

    def get_settings(self) -> list[Setting]:
##        return []
        settings = super().get_settings()
        settings.append(Setting('duration', 'max. Dauer', self.duration,
                                type='number', min=0, max=7*24*60*60, step=60*60))
        return settings

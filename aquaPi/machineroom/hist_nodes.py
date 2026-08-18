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
    ValueLst = list[str | float | None]

    def __init__(self):
        pass

    def add_field(self, name: str) -> None:
        pass

    @staticmethod
    def _insert(result: dict[int, 'TimeDb.ValueLst'], start: int,
                ts: int, idx: int, val: str | float | None) -> None:
        """ insert one (timestamp, series-index, value) triple into
            `result`, creating a new all-None row for `ts` if this is
            the first value seen at that timestamp. Values at or before
            `start` are folded into the `start` row itself. Shared by
            every TimeDb.query() implementation - only how they produce
            each triple differs.
        """
        if ts <= start:
            result[start][idx] = val
        else:
            if ts not in result:
                result[ts] = [None] * len(result[0])
            result[ts][idx] = val

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

    def __init__(self, capacity: int):
        """ in-memory storage is limited to {capacity} hours
        """
        super().__init__()
        self.capacity = capacity

    def add_field(self, name: str) -> None:
        super().add_field(name)
        TimeDbMemory._store.setdefault(name, deque(maxlen=self.capacity * 60 * 60))  # 1/sec

    def feed(self, name: str, value: int | float) -> None:
        with TimeDbMemory._store_lock:
            TimeDbMemory._store.setdefault(name, deque(maxlen=self.capacity * 60 * 60))  # 1/sec

            now = int(time())
            series = TimeDbMemory._store[name]
            if (len(series) == 0 or series[-1][0] != now):
                series.append((now, value))
            else:
                # multiple values for same second, build average
                series[-1] = (now, (series[-1][1] + value) / 2)

            # purge expired data
            while series[0][0] < now - self.capacity * 60 * 60:
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
            result[start] = [None] * len(result[0])
            for idx, name in enumerate(node_names):
                series = TimeDbMemory._store[name]
                for measurement in series:
                    (ts, val) = measurement
                    self._insert(result, start, ts, idx, val)

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
                        # seed row per series: its most recent value
                        # strictly before `start`, timestamped exactly at
                        # `start` so it sorts as the window's first known
                        # value - without this, a series that last changed
                        # before `start` (e.g. an infrequently-posting
                        # ScheduleInput) shows no history at all until its
                        # next in-window change, even though its state
                        # going into the window is perfectly well known.
                        # LATEST ON is QuestDB's own "most recent per
                        # partition" lookup; FILL(PREV) below then carries
                        # this seed forward same as any other row.
                        seeded = SQL("""
                            SELECT to_utc({start} * 1000000L, {tz}) ts, node_id, value
                              FROM value
                              WHERE ts < to_utc({start} * 1000000L, {tz})
                                AND node_id IN ({nodes})
                              LATEST ON ts PARTITION BY node_id
                            UNION ALL
                            SELECT ts, node_id, value
                              FROM value
                              WHERE ts >= to_utc({start} * 1000000L, {tz})
                                AND node_id IN ({nodes})
                            """).format(tz=Literal(self.timezone), start=Literal(start),
                                        nodes=q_names)
                        if step <= 0:
                            # unsampled = raw data
                            qry = SQL("""
                              SELECT to_timezone(ts,{tz}) ts, node_id, value
                                FROM ({seeded}) timestamp(ts)
                                ORDER BY ts,node_id;
                              """).format(tz=Literal(self.timezone), seeded=seeded)
                        else:
                            # NOTE: this used to go through an intermediate
                            # `SAMPLE BY 1s FILL(PREV)` pass before the real
                            # downsample below - dropped 2026-08-12, it made
                            # QuestDB materialize one synthetic row per
                            # second per series across the *entire*
                            # requested window before ever downsampling
                            # (e.g. ~590x slower for a 3-series, 1-year
                            # query - 16s vs 27ms measured). FILL(PREV)
                            # carries the seed row forward correctly at any
                            # SAMPLE BY granularity, so the 1s intermediate
                            # step wasn't needed for that semantics - verified
                            # identical output (mod ~1e-13 float rounding
                            # from a different averaging order) against the
                            # two-stage version for both single- and
                            # multi-series queries before making this change.
                            qry = SQL("""
                              SELECT to_timezone(ts,{tz}) span, node_id id, avg(value)
                                FROM ({seeded}) timestamp(ts)
                                SAMPLE BY {step}s FILL (PREV) ALIGN TO CALENDAR
                                GROUP BY ts,node_id ORDER BY span,node_id;
                              """).format(tz=Literal(self.timezone),
                                          step=Literal(step),
                                          seeded=seeded)
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
            result[start] = [None] * len(result[0])
            for row in recs:
                (dt_tm, node, val) = row
                ts = int(dt_tm.timestamp())  # max resolution is 1sec
                idx = names.index(node)
                self._insert(result, start, ts, idx, val)

            # null out the unchanged values, this safes processing time for
            # rare events in chart - but keep the bucket right before a real
            # change too (restoring it if it was already nulled out), so a
            # long idle run ends with a "flat here, then jumps" pair right
            # at the transition instead of one point far in the past. Without
            # this, a non-stepped (analog/percent) line chart with
            # spanGaps=true draws a straight ramp across the whole idle gap
            # up to the change, instead of staying flat until just before it.
            prev = result[start].copy()
            prev_ts = start
            for ts in result.keys():
                if ts <= start:
                    continue
                for idx, _ in enumerate(node_names):
                    if prev[idx] is None:
                        prev[idx] = result[ts][idx]
                    elif result[ts][idx] == prev[idx]:
                        result[ts][idx] = None
                    elif result[ts][idx] is not None:
                        if result[prev_ts][idx] is None:
                            result[prev_ts][idx] = prev[idx]
                        prev[idx] = result[ts][idx]
                prev_ts = ts
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
    _receives_kind = 'multi'

    @property
    def capacity(self) -> int:
        return self._capacity

    @capacity.setter
    def capacity(self, capacity: int) -> None:
        # TimeDbMemory's deque(maxlen=...) insists on a strict int; the API
        # delivers capacity as seconds/factor, which is a float even for
        # whole-hour values (e.g. 86400/3600 == 24.0)
        self._capacity = int(capacity)

    def __init__(self, name: str, receives: Iterable[str],
                 capacity: int = 24, _cont: bool = False):
        super().__init__(name, receives, _cont=_cont)
        self.capacity = capacity
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
            self.db = TimeDbMemory(self.capacity)
            log.brief('Recording history %s in main memory with limited depth of %dh!', name, self.capacity)
        for rcv in self.receives:
            self.db.add_field(rcv)

    def __getstate__(self) -> dict[str, Any]:
        state = super().__getstate__()
        state['capacity'] = self.capacity
        state['memory_only'] = isinstance(self.db, TimeDbMemory)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        # TEMPORARY: 'duration' was renamed to 'capacity' 2026-08-12; this
        # fallback only matters for a developer's already-saved local
        # topo.sqlite from before the rename (no production data exists
        # yet) - safe to delete this fallback (keep just state['capacity'])
        # once everyone's local DB has been re-saved at least once.
        capacity = state.get('capacity', state.get('duration', 24))
        History.__init__(self, state['name'], state['receives'],
                         capacity=capacity, _cont=True)

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
        settings = super().get_settings()
        schema = {s.key: s for s in type(self).get_settings_schema()}
        settings.append(self._fill_setting(schema['capacity']))
        return settings

    @classmethod
    def get_settings_schema(cls) -> list[Setting]:
        schema = super().get_settings_schema()
        schema.append(Setting('capacity', 'capacity', 24 * 60*60,
                              type='duration', min=0, max=7*24*60*60, step=60*60,
                              factor=60*60))
        return schema

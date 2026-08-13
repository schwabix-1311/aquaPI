#!/usr/bin/env python3
""" Tests for the TimeDb query-assembly consolidation (aquaPi/machineroom/
    hist_nodes.py): TimeDbMemory.query() and TimeDbQuest.query() both used
    to duplicate this "fold into the start row, else create a new one"
    logic - now shared via TimeDb._insert(). No existing test exercised
    this directly (only indirectly, via the whole suite still passing),
    so this fills that gap.
"""
# pylint: disable=protected-access
# _insert() is the shared internal helper under test here - calling it
# directly is the point, not an accident.

import time as time_module

import pytest

from aquaPi import db as db_module
from aquaPi.machineroom import hist_nodes
from aquaPi.machineroom.hist_nodes import History, TimeDb, TimeDbMemory


def test_insert_folds_values_at_or_before_start_into_start_row():
    result = {0: ['a', 'b'], 5: [None, None]}

    TimeDb._insert(result, start=5, ts=3, idx=0, val=1.0)
    TimeDb._insert(result, start=5, ts=5, idx=1, val=2.0)

    assert result == {0: ['a', 'b'], 5: [1.0, 2.0]}


def test_insert_creates_a_new_row_for_a_timestamp_after_start():
    result = {0: ['a', 'b'], 5: [None, None]}

    TimeDb._insert(result, start=5, ts=10, idx=0, val=3.0)
    TimeDb._insert(result, start=5, ts=10, idx=1, val=4.0)

    assert result[5] == [None, None]
    assert result[10] == [3.0, 4.0]


def test_insert_does_not_mutate_the_shared_valuelst_type_alias():
    # regression check for the fixed typo (`result[start] = TimeDb.ValueLst
    # = [...]`), which used to clobber this class attribute on every query
    before = TimeDb.ValueLst
    result = {0: ['a'], 5: [None]}
    TimeDb._insert(result, start=5, ts=5, idx=0, val=1.0)
    assert TimeDb.ValueLst is before


def test_timedb_memory_query_assembles_multi_series_multi_timestamp_result(monkeypatch):
    monkeypatch.setattr(TimeDbMemory, '_store', {})
    monkeypatch.setattr(hist_nodes, 'time', lambda: 1000.0)
    db = TimeDbMemory(capacity=1)

    db.feed('sensor_a', 1.0)
    db.feed('sensor_b', 2.0)

    # start is after this feed -> both values fold into the start row
    result = db.query(['sensor_a', 'sensor_b'], start=1000)
    assert result[0] == ['sensor_a', 'sensor_b']
    assert result[1000] == [1.0, 2.0]

    # start is before this feed -> a new row is created at the feed's ts,
    # left None for any series that has no value yet at that timestamp
    monkeypatch.setattr(hist_nodes, 'time', lambda: 1010.0)
    db.feed('sensor_a', 3.0)
    result = db.query(['sensor_a', 'sensor_b'], start=1000)
    assert result[1000] == [1.0, 2.0]
    assert result[1010] == [3.0, None]


def test_history_getstate_reports_capacity_and_memory_only(monkeypatch):
    monkeypatch.setattr(hist_nodes, 'QUEST_DB', False)

    hist = History('Verlauf', ['sensor'], capacity=3)
    state = hist.__getstate__()

    assert state['capacity'] == 3
    assert state['memory_only'] is True


def test_history_setstate_falls_back_to_pre_rename_duration_key(monkeypatch):
    # TEMPORARY: covers the back-compat fallback in History.__setstate__()
    # for a state dict saved before 'duration' was renamed to 'capacity' -
    # delete this test alongside that fallback once it's removed.
    monkeypatch.setattr(hist_nodes, 'QUEST_DB', False)

    hist = History.__new__(History)
    hist.__setstate__({'name': 'Verlauf', 'receives': ['sensor'], 'duration': 5})

    assert hist.capacity == 5


def test_build_node_history_uses_capacity_field(monkeypatch):
    monkeypatch.setattr(hist_nodes, 'QUEST_DB', False)

    node = db_module.build_node('History', 'Verlauf', ['sensor'], {'capacity': 2})

    assert node.capacity == 2


@pytest.mark.questdb
def test_timedb_quest_query_seeds_start_row_from_before_the_window():
    """ integration test against a real, reachable QuestDB instance -
        the actual bug this fixes: a series whose last change was
        before the query's `start` used to show no history at all
        until its next in-window change (TimeDbQuest._query()'s SQL
        only ever fetched `ts >= start`), even though its state going
        into the window was perfectly well known. Fixed by having the
        query itself UNION in a LATEST ON ... WHERE ts < start seed row,
        timestamped exactly at `start`, for QuestDB's own FILL(PREV) to
        carry forward - see TimeDbQuest._query().

        Uses a throwaway, uniquely-named node id so this neither reads
        nor depends on real production data; the few leftover rows it
        writes are harmless and not cleaned up (QuestDB's DELETE
        support is limited).
    """
    from aquaPi.machineroom.hist_nodes import QUEST_DB, TimeDbQuest
    if not QUEST_DB:
        pytest.skip('psycopg not installed')

    db = TimeDbQuest()
    node = f'_test_seed_{int(time_module.time() * 1000)}'

    db.feed(node, 42.0)
    time_module.sleep(1.2)  # land the feed in a distinct second, before `start`

    start = int(time_module.time())
    result = db.query([node], start=start, step=60)

    assert result[0] == [node]
    assert result[start] == [42.0]


@pytest.mark.questdb
def test_timedb_quest_query_keeps_anchor_point_before_a_change():
    """ integration test against a real, reachable QuestDB instance -
        the "ramp" bug: TimeDbQuest.query()'s "null out the unchanged
        values" step used to null every bucket of a flat run except its
        very first one. A non-stepped (analog/percent) chart line with
        spanGaps=true then drew a straight ramp from that first point,
        however long ago it was, all the way to the next real change -
        instead of staying flat until just before it. Fixed by also
        restoring (un-nulling) the single bucket immediately before a
        real change, so the flat run always ends with a
        "still-old-value, then new-value" pair right at the transition.

        Uses a throwaway, uniquely-named node id, same rationale as
        test_timedb_quest_query_seeds_start_row_from_before_the_window.
    """
    from aquaPi.machineroom.hist_nodes import QUEST_DB, TimeDbQuest
    if not QUEST_DB:
        pytest.skip('psycopg not installed')

    db = TimeDbQuest()
    node = f'_test_anchor_{int(time_module.time() * 1000)}'

    start = int(time_module.time())
    db.feed(node, 1.0)
    time_module.sleep(3.2)  # idle span, several 1s buckets filled via FILL(PREV)
    db.feed(node, 2.0)
    time_module.sleep(1.2)

    result = db.query([node], start=start, step=1)

    values = {ts: row[0] for ts, row in result.items() if ts != 0}
    change_ts = max(ts for ts, val in values.items() if val == 2.0)

    assert values.get(change_ts - 1) == 1.0

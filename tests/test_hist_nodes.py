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

from aquaPi.machineroom import hist_nodes
from aquaPi.machineroom.hist_nodes import TimeDb, TimeDbMemory


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
    db = TimeDbMemory(duration=1)

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

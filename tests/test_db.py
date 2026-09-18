#!/usr/bin/env python3
""" Tests for the SQLite persistence layer in aquaPi/db.py

    All tests use the simulation-safe node types only (no real hardware
    access is needed, the FileDriver/simulation layer is used implicitly
    by passing plain string ports that don't resolve to real GPIO/I2C).
"""

import json

import pytest

from aquaPi import db
from aquaPi.driver import create_io_registry
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.in_nodes import AnalogInput, ScheduleInput
from aquaPi.machineroom.ctrl_nodes import MinimumCtrl
from aquaPi.machineroom.out_nodes import SwitchDevice
from aquaPi.machineroom.aux_nodes import AvgAux
from aquaPi.machineroom.alert_nodes import Alert, AlertAbove, AlertBelow


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    """ the node drivers (even in simulation) need the IoRegistry singleton """
    create_io_registry()


def _build_sample_bus() -> MsgBus:
    # NOTE: port='' avoids any dependency on real (or simulated) hardware
    # port drivers - it just skips driver creation, which is all we need
    # to exercise the persistence layer.
    bus = MsgBus(threaded=False)

    sensor1 = AnalogInput('Wasser', '', 25.0, '°C', avg=1, interval=60)
    sensor2 = AnalogInput('Raumluft', '', 24.0, '°C', avg=2, interval=60)
    ctrl = MinimumCtrl('Heizen', sensor1.id, 25.0, hysteresis=0.2)
    out = SwitchDevice('Heizstab', ctrl.id, '', inverted=False)
    avg = AvgAux('Mittel', {sensor1.id, sensor2.id})
    schedule = ScheduleInput('Zeitplan', 24 * 3600, 11 * 3600, anchor='10:00')

    alert = Alert('Warnungen',
                  {AlertAbove(sensor1.id, 26.0),
                   AlertBelow(sensor1.id, 24.0)},
                  '', repeat=3600)

    for node in (sensor1, sensor2, ctrl, out, avg, schedule, alert):
        node.plugin(bus)

    return bus


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / 'wiring.sqlite')


def test_init_db_creates_schema(db_path):
    conn = db.get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


def test_save_and_load_roundtrip(db_path):
    bus = _build_sample_bus()
    original_ids = {n.id for n in bus.nodes}
    original_types = {n.id: type(n).__name__ for n in bus.nodes}

    db.save_wiring(bus, db_path)
    bus.teardown()
    assert db.wiring_exists(db_path)

    restored = db.load_wiring(db_path)
    try:
        restored_ids = {n.id for n in restored.nodes}
        assert restored_ids == original_ids

        for node in restored.nodes:
            assert type(node).__name__ == original_types[node.id]
    finally:
        restored.teardown()


def test_alert_conditions_are_restored(db_path):
    bus = _build_sample_bus()
    db.save_wiring(bus, db_path)
    bus.teardown()

    restored = db.load_wiring(db_path)
    try:
        alert = restored.get_node('warnungen')
        assert isinstance(alert, Alert)
        assert len(alert.conditions) == 2
        classes = {type(c).__name__ for c in alert.conditions}
        assert classes == {'AlertAbove', 'AlertBelow'}
        for cond in alert.conditions:
            assert cond.node_id == 'wasser'
    finally:
        restored.teardown()


def test_params_are_plain_json(db_path):
    """ ensure no pickle-specific / non-JSON data ever hits the DB """
    bus = _build_sample_bus()
    db.save_wiring(bus, db_path)
    bus.teardown()

    conn = db.get_connection(db_path)
    try:
        rows = conn.execute('SELECT params FROM nodes').fetchall()
        assert len(rows) > 0
        for row in rows:
            # must round-trip through plain json without error
            json.loads(row['params'])
            # and must not contain a pickle opcode marker
            assert 'py/object' not in row['params']
    finally:
        conn.close()


def test_save_replaces_previous_wiring(db_path):
    bus = _build_sample_bus()
    db.save_wiring(bus, db_path)
    bus.teardown()

    smaller_bus = MsgBus(threaded=False)
    single = AnalogInput('Only', '', 20.0, '°C')
    single.plugin(smaller_bus)
    db.save_wiring(smaller_bus, db_path)
    smaller_bus.teardown()

    restored = db.load_wiring(db_path)
    try:
        assert {n.id for n in restored.nodes} == {'only'}
    finally:
        restored.teardown()


def test_load_wiring_prunes_dangling_references_to_a_node_that_failed_to_restore(db_path,
                                                                                 monkeypatch):
    """ regression test for a real production incident: a node that
        fails to deserialize (here: corrupted saved params) was silently
        skipped, but every OTHER node still wired to it kept a dangling
        reference forever - nothing else ever gets a chance to prune it,
        since the normal delete-time pruning (api_delete_node/
        apply_config_diff) only runs against a node bus.get_node() can
        actually find, and one that failed to load was never there to
        find. This left e.g. a History node's chart hung on a receives
        entry that no longer resolved to anything.
    """
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    avg = AvgAux('Mittel', {sensor.id})
    dependent = MinimumCtrl('Heizen', avg.id, 25.0, hysteresis=0.2)   # wired to 'avg'
    sibling = MinimumCtrl('Kuehlen', sensor.id, 25.0, hysteresis=0.2)  # unaffected, wired to 'wasser'
    for node in (sensor, avg, dependent, sibling):
        node.plugin(bus)
    db.save_wiring(bus, db_path)
    bus.teardown()

    # corrupt 'avg's saved params so _deserialize_node raises (KeyError on
    # the missing 'receives') - simulates any real deserialize failure,
    # not the specific float/int bug that originally triggered this
    conn = db.get_connection(db_path)
    try:
        row = conn.execute("SELECT params FROM nodes WHERE id='mittel'").fetchone()
        params = json.loads(row['params'])
        del params['receives']
        conn.execute("UPDATE nodes SET params=? WHERE id='mittel'", (json.dumps(params),))
        conn.commit()
    finally:
        conn.close()

    # a real deployment with Email/Telegram configured would notify and
    # keep running rather than hard-abort (see the startup-failure
    # notify/abort behavior this deliberately doesn't touch) - simulate
    # that so this test can inspect the resulting bus
    monkeypatch.setattr(db, '_notify_startup_failures', lambda failures: True)

    restored = db.load_wiring(db_path)
    try:
        assert restored.get_node('mittel') is None   # failed to restore, as expected
        assert restored.get_node('heizen').receives == []   # pruned
        # unaffected sibling, confirms pruning is targeted, not a wipe
        assert restored.get_node('kuehlen').receives == ['wasser']
    finally:
        restored.teardown()

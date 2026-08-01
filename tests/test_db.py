#!/usr/bin/env python3
""" Tests for the SQLite persistence layer in aquaPi/db.py

    All tests use the simulation-safe node types only (no real hardware
    access is needed, the FileDriver/simulation layer is used implicitly
    by passing plain string ports that don't resolve to real GPIO/I2C).
"""

import json
import pickle

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
    schedule = ScheduleInput('Zeitplan', '* 10-20 * * *')

    alert = Alert('Warnungen',
                  {AlertAbove(sensor1.id, 26.0),
                   AlertBelow(sensor1.id, 24.0)},
                  '', repeat=3600)

    for node in (sensor1, sensor2, ctrl, out, avg, schedule, alert):
        node.plugin(bus)

    return bus


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / 'topo.sqlite')


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

    db.save_topology(bus, db_path)
    bus.teardown()
    assert db.topology_exists(db_path)

    restored = db.load_topology(db_path)
    try:
        restored_ids = {n.id for n in restored.nodes}
        assert restored_ids == original_ids

        for node in restored.nodes:
            assert type(node).__name__ == original_types[node.id]
    finally:
        restored.teardown()


def test_alert_conditions_are_restored(db_path):
    bus = _build_sample_bus()
    db.save_topology(bus, db_path)
    bus.teardown()

    restored = db.load_topology(db_path)
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
    db.save_topology(bus, db_path)
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


def test_save_replaces_previous_topology(db_path):
    bus = _build_sample_bus()
    db.save_topology(bus, db_path)
    bus.teardown()

    smaller_bus = MsgBus(threaded=False)
    single = AnalogInput('Only', '', 20.0, '°C')
    single.plugin(smaller_bus)
    db.save_topology(smaller_bus, db_path)
    smaller_bus.teardown()

    restored = db.load_topology(db_path)
    try:
        assert {n.id for n in restored.nodes} == {'only'}
    finally:
        restored.teardown()


def test_migrate_pickle_to_sqlite(tmp_path):
    bus = _build_sample_bus()
    original_ids = {n.id for n in bus.nodes}

    pickle_path = str(tmp_path / 'topo.pickle')
    with open(pickle_path, 'wb') as p:
        pickle.dump(bus, p, protocol=pickle.HIGHEST_PROTOCOL)
    bus.teardown()

    db_path = str(tmp_path / 'topo.sqlite')
    migrated = db.migrate_pickle_to_sqlite(pickle_path, db_path)
    assert migrated is True

    # original file must be kept as backup, never deleted
    import os
    assert not os.path.exists(pickle_path)
    assert os.path.exists(pickle_path + '.bak')

    restored = db.load_topology(db_path)
    try:
        assert {n.id for n in restored.nodes} == original_ids
    finally:
        restored.teardown()

    # running migration again must be a no-op (topology already exists)
    with open(pickle_path + '.bak', 'rb') as p:
        pass
    migrated_again = db.migrate_pickle_to_sqlite(pickle_path + '.bak', db_path)
    assert migrated_again is False


def test_migrate_pickle_to_sqlite_no_source(tmp_path):
    db_path = str(tmp_path / 'topo.sqlite')
    assert db.migrate_pickle_to_sqlite(str(tmp_path / 'does_not_exist.pickle'), db_path) is False
    assert not db.topology_exists(db_path)


def test_migrate_pickle_to_sqlite_damaged_file_does_not_crash(tmp_path):
    """ a broken/incompatible topo.pickle (e.g. referencing a module that no
        longer exists after a refactoring) must not crash the app - it is
        simply left untouched and the caller falls back to a fresh topology
    """
    pickle_path = str(tmp_path / 'topo.pickle')
    with open(pickle_path, 'wb') as p:
        p.write(b'not a valid pickle stream at all')

    db_path = str(tmp_path / 'topo.sqlite')
    migrated = db.migrate_pickle_to_sqlite(pickle_path, db_path)
    assert migrated is False

    # damaged file must be kept untouched, not renamed/deleted
    import os
    assert os.path.exists(pickle_path)
    assert not os.path.exists(pickle_path + '.bak')
    assert not db.topology_exists(db_path)

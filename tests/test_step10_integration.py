#!/usr/bin/env python3
""" Step 10: overall verification that Steps 1-9 work together correctly.
    Scenarios (see plan, "Key Scenarios" / Step 10):
    - combined migration of a legacy config.json (Email/Telegram) and a
      legacy topo.pickle into the new SQLite persistence, simulation
      starts without errors
    - two simulated users with different dashboards and alert channels
      show correctly separated results
    - all simulated nodes remain reachable via the new plain-JSON API
"""

import json
import os
import pickle
from http import HTTPStatus

import pytest
from flask import Flask

import aquaPi
from aquaPi import auth, db, api
from aquaPi.driver import create_io_registry
from aquaPi.machineroom import MachineRoom
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.in_nodes import AnalogInput
from aquaPi.machineroom.ctrl_nodes import MinimumCtrl
from aquaPi.machineroom.alert_nodes import Alert, AlertAbove


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    """ the IoRegistry singleton must exist before any node using
        IoRegistry.get() is constructed, regardless of which other test
        modules already ran in this session
    """
    create_io_registry()


# --- Scenario 1: combined config.json + topo.pickle migration ------------


def _build_legacy_bus() -> MsgBus:
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)
    ctrl = MinimumCtrl('Heizen', sensor.id, setpoint=24.0, hysteresis=0.5)
    ctrl.plugin(bus)
    alert = Alert('Warnung', AlertAbove(sensor.id, limit=30.0, duration=5), port='')
    alert.plugin(bus)
    return bus


def test_combined_legacy_migration_starts_simulation_cleanly(tmp_path):
    instance_path = str(tmp_path)

    # legacy config.json with Email/Telegram credentials
    legacy_cfg = {
        'Email': {'server': 'smtp.example.com', 'login': 'me', 'pwd': 'secret',
                  'from': 'me@example.com', 'to': 'you@example.com'},
        'Telegram': [{'bot_token': 'tok123', 'chat_name': 'aquaPi', 'chat_id': 42}],
    }
    with open(os.path.join(instance_path, 'config.json'), 'w', encoding='utf8') as f:
        json.dump(legacy_cfg, f)

    # legacy topo.pickle with a small hand-built bus
    legacy_bus = _build_legacy_bus()
    legacy_ids = {n.id for n in legacy_bus.nodes}
    with open(os.path.join(instance_path, 'topo.pickle'), 'wb') as f:
        pickle.dump(legacy_bus, f, protocol=pickle.HIGHEST_PROTOCOL)
    legacy_bus.teardown()

    mr = MachineRoom({'INSTANCE_PATH': instance_path})
    try:
        # topology was migrated, not replaced by the default topology
        assert {n.id for n in mr.bus.nodes} == legacy_ids

        # original pickle kept as backup, DB now exists
        assert not os.path.exists(os.path.join(instance_path, 'topo.pickle'))
        assert os.path.exists(os.path.join(instance_path, 'topo.pickle.bak'))
        assert db.topology_exists(mr.globals['BUS_TOPO'])

        # notification config was migrated into the users DB
        users_db = mr.globals['USERS_DB']
        assert db.get_notification_config(users_db, 'Email')[0]['login'] == 'me'
        assert db.get_notification_config(users_db, 'Telegram')[0]['bot_token'] == 'tok123'
    finally:
        mr.bus.teardown()


def test_fresh_start_without_any_legacy_files_creates_default_topology(tmp_path):
    instance_path = str(tmp_path)
    mr = MachineRoom({'INSTANCE_PATH': instance_path})
    try:
        # default simulated topology (TEST_PH/SIM_LIGHT/SIM_TEMP) has 13 nodes
        assert len(mr.bus.nodes) == 13
        assert db.topology_exists(mr.globals['BUS_TOPO'])
    finally:
        mr.bus.teardown()


def test_restart_after_migration_is_stable(tmp_path):
    """ a 2nd MachineRoom instance against the same instance dir must load
        the already-migrated SQLite topology unchanged (no re-migration,
        no pickle fallback)
    """
    instance_path = str(tmp_path)
    legacy_bus = _build_legacy_bus()
    legacy_ids = {n.id for n in legacy_bus.nodes}
    with open(os.path.join(instance_path, 'topo.pickle'), 'wb') as f:
        pickle.dump(legacy_bus, f, protocol=pickle.HIGHEST_PROTOCOL)
    legacy_bus.teardown()

    mr1 = MachineRoom({'INSTANCE_PATH': instance_path})
    mr1.bus.teardown()

    mr2 = MachineRoom({'INSTANCE_PATH': instance_path})
    try:
        assert {n.id for n in mr2.bus.nodes} == legacy_ids
        # migration must not run twice (legacy file already renamed to .bak)
        assert not os.path.exists(os.path.join(instance_path, 'topo.pickle'))
    finally:
        mr2.bus.teardown()


# --- Scenario 2 & 3: two users, separate dashboards/alert channels, -------
# --- full node list via the plain-JSON API --------------------------------


@pytest.fixture
def bus():
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.group = 'Becken 1'
    sensor.plugin(bus)

    ctrl = MinimumCtrl('Heizen', sensor.id, setpoint=24.0, hysteresis=0.5)
    ctrl.group = 'Becken 1'
    ctrl.plugin(bus)

    alert = Alert('Warnung', AlertAbove(sensor.id, limit=30.0, duration=5), port='')
    alert.plugin(bus)

    yield bus
    bus.teardown()


class _FakeMachineRoom:
    def __init__(self, bus: MsgBus):
        self.bus = bus


@pytest.fixture
def app(tmp_path, bus):
    app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
    app.config['INSTANCE_PATH'] = str(tmp_path)
    app.config['TESTING'] = True

    auth.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)
    app.extensions['machineroom'] = _FakeMachineRoom(bus)

    @app.route('/', endpoint='spa.spa')
    def spa_stub():
        return 'spa'

    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password})


def test_two_users_have_separated_dashboards_and_alert_prefs(app, client):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    u1 = db.create_user(users_db, 'alice', 'alicePass1', role='viewer')
    u2 = db.create_user(users_db, 'bob', 'bobPass123', role='operator')

    db.set_dashboard(users_db, u1, [{'controller_id': 'heizen', 'group': 'Becken 1'}])
    db.set_dashboard(users_db, u2, [{'controller_id': 'warnung', 'group': 'Becken 1'}])
    db.set_user_notification_pref(users_db, u1, 'warnung', 'email')
    db.set_user_notification_pref(users_db, u2, 'warnung', 'telegram')

    _login(client, 'alice', 'alicePass1')
    resp = client.get('/api/dashboard/')
    assert resp.get_json() == [{'controller_id': 'heizen', 'group': 'Becken 1'}]
    resp = client.get('/api/notifications/prefs')
    assert resp.get_json() == [{'alert_node_id': 'warnung', 'channel': 'email'}]
    client.get('/logout')

    _login(client, 'bob', 'bobPass123')
    resp = client.get('/api/dashboard/')
    assert resp.get_json() == [{'controller_id': 'warnung', 'group': 'Becken 1'}]
    resp = client.get('/api/notifications/prefs')
    assert resp.get_json() == [{'alert_node_id': 'warnung', 'channel': 'telegram'}]

    # underlying storage is confirmed separated too, not just via API
    prefs = db.get_prefs_for_alert(users_db, 'warnung')
    channel_by_user = {p['user_id']: p['channel'] for p in prefs}
    assert channel_by_user == {u1: 'email', u2: 'telegram'}


def test_all_nodes_reachable_via_plain_json_api(app, client):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    db.create_user(users_db, 'viewer1', 'viewerPass1', role='viewer')
    _login(client, 'viewer1', 'viewerPass1')

    resp = client.get('/api/nodes/')
    assert resp.status_code == HTTPStatus.OK
    ids = resp.get_json()
    assert set(ids) == {'wasser', 'heizen', 'warnung'}

    for node_id in ids:
        resp = client.get(f'/api/nodes/{node_id}')
        assert resp.status_code == HTTPStatus.OK
        body = resp.get_json()
        assert body['result'] == 'SUCCESS'
        assert body['data']['id'] == node_id
        # no jsonpickle artifacts anywhere
        raw = resp.get_data(as_text=True)
        assert 'py/object' not in raw

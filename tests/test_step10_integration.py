#!/usr/bin/env python3
""" Step 10: overall verification that Steps 1-9 work together correctly.
    Scenarios (see plan, "Key Scenarios" / Step 10):
    - migration of a legacy config.json's Email/Telegram credentials into
      the new SQLite persistence, simulation starts without errors
    - two simulated users with different dashboards and alert channels
      show correctly separated results
    - all simulated nodes remain reachable via the new plain-JSON API
"""

import json
import os
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


# --- Scenario 1: legacy config.json migration -----------------------------


def test_legacy_config_json_migration_starts_simulation_cleanly(tmp_path):
    instance_path = str(tmp_path)

    # legacy config.json with Email/Telegram credentials
    legacy_cfg = {
        'Email': {'server': 'smtp.example.com', 'login': 'me', 'pwd': 'secret',
                  'from': 'me@example.com', 'to': 'you@example.com'},
        'Telegram': [{'bot_token': 'tok123', 'chat_name': 'aquaPi', 'chat_id': 42}],
    }
    with open(os.path.join(instance_path, 'config.json'), 'w', encoding='utf8') as f:
        json.dump(legacy_cfg, f)

    # DEFAULT_CONFIG must be anything other than 'wiring' (the maintainer's own
    # real/production hardware setup) or this would build that instead of a
    # simulated wiring - see test_fresh_start_without_any_legacy_files_
    # creates_default_wiring below for why that matters.
    mr = MachineRoom({'INSTANCE_PATH': instance_path, 'DEFAULT_CONFIG': 'pytest'})
    try:
        # no wiring to migrate, so a fresh default one is created
        assert len(mr.bus.nodes) > 0
        assert db.wiring_exists(mr.globals['BUS_WIRING'])

        # notification config was migrated into the users DB
        users_db = mr.globals['USERS_DB']
        assert db.get_notification_config(users_db, 'Email')[0]['login'] == 'me'
        assert db.get_notification_config(users_db, 'Telegram')[0]['bot_token'] == 'tok123'
    finally:
        mr.bus.teardown()


def test_config_json_global_keys_are_reimported_every_start(tmp_path):
    """ unlike the Email/Telegram sub-migration above (which moves out of
        config.json once and for all, into the users DB), the rest of
        config.json has no editor yet - it must stay a live merge into
        self.globals on every start, not a one-time import, so an admin
        can still hand-edit it and have the change take effect on restart
    """
    instance_path = str(tmp_path)
    cfg_path = os.path.join(instance_path, 'config.json')

    with open(cfg_path, 'w', encoding='utf8') as f:
        json.dump({'SOME_CUSTOM_SETTING': 'first'}, f)

    mr1 = MachineRoom({'INSTANCE_PATH': instance_path, 'DEFAULT_CONFIG': 'pytest'})
    assert mr1.globals['SOME_CUSTOM_SETTING'] == 'first'
    mr1.bus.teardown()

    with open(cfg_path, 'w', encoding='utf8') as f:
        json.dump({'SOME_CUSTOM_SETTING': 'second'}, f)

    mr2 = MachineRoom({'INSTANCE_PATH': instance_path, 'DEFAULT_CONFIG': 'pytest'})
    try:
        assert mr2.globals['SOME_CUSTOM_SETTING'] == 'second'
    finally:
        mr2.bus.teardown()


def test_fresh_start_without_any_legacy_files_creates_default_wiring(tmp_path):
    instance_path = str(tmp_path)
    # DEFAULT_CONFIG must be anything other than 'wiring' (the maintainer's
    # own real/production hardware setup - see MachineRoom.create_default_nodes())
    # or this test would build that instead of the intended simulated
    # dev/test node set: it needs hardware ports and notification channels
    # that don't exist in this fresh test instance (DriverInvalidPortError),
    # and would write real rows into the real, shared QuestDB instance
    # under the same node names as production (see machineroom/__init__.py)
    mr = MachineRoom({'INSTANCE_PATH': instance_path, 'DEFAULT_CONFIG': 'pytest'})
    try:
        # default simulated wiring (TEST_PH/SIM_LIGHT/SIM_TEMP) has 13 nodes
        assert len(mr.bus.nodes) == 13
        assert db.wiring_exists(mr.globals['BUS_WIRING'])
    finally:
        mr.bus.teardown()


def test_restart_reloads_existing_sqlite_wiring_unchanged(tmp_path):
    """ a 2nd MachineRoom instance against the same instance dir must load
        the already-persisted SQLite wiring unchanged, not recreate the
        default one
    """
    instance_path = str(tmp_path)

    mr1 = MachineRoom({'INSTANCE_PATH': instance_path, 'DEFAULT_CONFIG': 'pytest'})
    node_ids = {n.id for n in mr1.bus.nodes}
    mr1.bus.teardown()

    mr2 = MachineRoom({'INSTANCE_PATH': instance_path, 'DEFAULT_CONFIG': 'pytest'})
    try:
        assert {n.id for n in mr2.bus.nodes} == node_ids
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


def test_two_users_have_separated_dashboards(app, client):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    u1 = db.create_user(users_db, 'alice', 'alicePass1', role='viewer')
    u2 = db.create_user(users_db, 'bob', 'bobPass123', role='operator')

    db.set_dashboard(users_db, u1, [{'controller_id': 'heizen', 'group': 'Becken 1'}])
    db.set_dashboard(users_db, u2, [{'controller_id': 'warnung', 'group': 'Becken 1'}])

    _login(client, 'alice', 'alicePass1')
    resp = client.get('/api/dashboard/')
    assert resp.get_json() == [{'controller_id': 'heizen', 'group': 'Becken 1'}]
    client.get('/logout')

    _login(client, 'bob', 'bobPass123')
    resp = client.get('/api/dashboard/')
    assert resp.get_json() == [{'controller_id': 'warnung', 'group': 'Becken 1'}]


def test_notification_prefs_api_get_open_put_admin_only(app, client):
    """ escalation config is a single, shared config per Alert node (not
        per-user - aquaPi's "users" are shared roles, not individual
        people): GET is read-only for operator+admin, PUT is admin-only.
        A viewer gets 403 on both. Two different admins must see the
        exact same shared config - that's the concrete proof the
        per-user dimension is gone.
    """
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    db.create_user(users_db, 'viewer1', 'viewerPass1', role='viewer')
    db.create_user(users_db, 'operator1', 'operatorPass1', role='operator')
    db.create_user(users_db, 'admin1', 'adminPass123', role='admin')
    db.create_user(users_db, 'admin2', 'adminPass456', role='admin')

    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/api/notifications/prefs')
    assert resp.status_code == HTTPStatus.FORBIDDEN
    resp = client.put('/api/notifications/prefs/warnung',
                      json={'escalation_channel': 'Telegram #1'})
    assert resp.status_code == HTTPStatus.FORBIDDEN
    client.get('/logout')

    _login(client, 'operator1', 'operatorPass1')
    resp = client.get('/api/notifications/prefs')
    assert resp.status_code == HTTPStatus.OK
    resp = client.put('/api/notifications/prefs/warnung',
                      json={'escalation_channel': 'Telegram #1'})
    assert resp.status_code == HTTPStatus.FORBIDDEN
    client.get('/logout')

    _login(client, 'admin1', 'adminPass123')
    resp = client.put('/api/notifications/prefs/warnung',
                      json={'escalation_channel': 'Telegram #1', 'escalation_after_minutes': 30})
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == {'alert_node_id': 'warnung', 'escalation_channel': 'Telegram #1',
                               'escalation_after_minutes': 30}

    resp = client.get('/api/notifications/prefs')
    assert resp.get_json() == [{'alert_node_id': 'warnung', 'escalation_channel': 'Telegram #1',
                                'escalation_after_minutes': 30}]
    client.get('/logout')

    # a 2nd, different admin must see the exact same shared config
    _login(client, 'admin2', 'adminPass456')
    resp = client.get('/api/notifications/prefs')
    assert resp.get_json() == [{'alert_node_id': 'warnung', 'escalation_channel': 'Telegram #1',
                                'escalation_after_minutes': 30}]

    # underlying storage is confirmed too, not just via API
    config = db.get_escalation_config(users_db, 'warnung')
    assert config == {'alert_node_id': 'warnung', 'escalation_channel': 'Telegram #1',
                      'escalation_after_minutes': 30}


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

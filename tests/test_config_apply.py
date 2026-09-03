#!/usr/bin/env python3
""" Tests for Step 15 (prioritized ahead of Step 18-30): the atomic
    bulk-apply endpoint POST /api/config/apply, the backend counterpart
    of the /config editor's client-side draft mode (Step 16).
"""

import os
from http import HTTPStatus

import pytest
from flask import Flask

import aquaPi
from aquaPi import auth, db, api
from aquaPi.driver import create_io_registry
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.in_nodes import AnalogInput
from aquaPi.machineroom.out_nodes import SwitchDevice
from aquaPi.machineroom.ctrl_nodes import MinimumCtrl
from aquaPi.machineroom.alert_nodes import Alert, AlertAbove


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


@pytest.fixture
def bus():
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    ctrl = MinimumCtrl('Heizen', sensor.id, setpoint=24.0, hysteresis=0.5)
    ctrl.plugin(bus)

    out = SwitchDevice('Heizstab', ctrl.id, '')
    out.plugin(bus)

    alert = Alert('Warnungen', AlertAbove(sensor.id, 30.0), '')
    alert.plugin(bus)

    yield bus
    bus.teardown()


class _FakeMachineRoom:
    def __init__(self, bus: MsgBus):
        self.bus = bus
        self.saved = 0

    def save_nodes(self, container):
        self.saved += 1


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


@pytest.fixture
def users(app):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    db.create_user(users_db, 'operator1', 'operatorPass1', role='operator')
    db.create_user(users_db, 'admin1', 'adminPass123', role='admin')


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


def test_apply_requires_admin(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.post('/api/config/apply', json={})
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_apply_empty_diff_is_noop(client, users, app):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/config/apply', json={})
    assert resp.status_code == HTTPStatus.OK
    assert app.extensions['machineroom'].saved == 0


def test_apply_mixed_diff_atomic(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-1', 'type': 'AnalogInput', 'name': 'Luft',
            'fields': {'unit': '°C'},
        }],
        'updates': [{'id': 'heizen', 'receives': ['tmp-1']}],
        'deletes': ['heizstab'],
    })
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()

    luft_id = data['id_map']['tmp-1']
    assert luft_id == 'luft'
    assert bus.get_node('luft') is not None
    assert bus.get_node('heizen').receives == ['luft']
    assert bus.get_node('heizstab') is None
    assert app.extensions['machineroom'].saved == 1


def test_apply_rejects_cycle_fully(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-1', 'type': 'AnalogInput', 'name': 'Luft',
            'fields': {'unit': '°C'},
        }],
        # heizstab receives from heizen; wiring heizen to receive from
        # heizstab would create a cycle - the whole diff must be rejected,
        # including the harmless 'Luft' create above
        'updates': [{'id': 'heizen', 'receives': ['heizstab']}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('luft') is None
    assert bus.get_node('heizen').receives == ['wasser']
    assert app.extensions['machineroom'].saved == 0


def test_apply_rejects_duplicate_name(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [
            {'temp_id': 'a', 'type': 'AnalogInput', 'name': 'Luft', 'fields': {'unit': '°C'}},
            {'temp_id': 'b', 'type': 'AnalogInput', 'name': 'Luft', 'fields': {'unit': '°C'}},
        ],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('luft') is None
    assert app.extensions['machineroom'].saved == 0


def test_apply_rejects_invalid_field(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'a', 'type': 'MinimumCtrl', 'name': 'NeuerCtrl',
            'receives': ['wasser'], 'fields': {},  # 'setpoint' is required
        }],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('neuerctrl') is None
    assert app.extensions['machineroom'].saved == 0


def test_apply_rejects_unknown_delete_id(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/config/apply', json={'deletes': ['doesnotexist']})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert app.extensions['machineroom'].saved == 0


def test_apply_temp_id_remap_between_two_new_nodes(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [
            {'temp_id': 't-sensor', 'type': 'AnalogInput', 'name': 'Luft',
             'fields': {'unit': '°C'}},
            {'temp_id': 't-ctrl', 'type': 'MinimumCtrl', 'name': 'Luftregler',
             'receives': ['t-sensor'], 'fields': {'setpoint': 20.0}},
        ],
    })
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()

    sensor_id = data['id_map']['t-sensor']
    ctrl_id = data['id_map']['t-ctrl']
    assert sensor_id == 'luft'
    assert ctrl_id == 'luftregler'
    assert bus.get_node(ctrl_id).receives == [sensor_id]
    assert app.extensions['machineroom'].saved == 1


def test_apply_persists_wiring_once(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/config/apply', json={
        'updates': [{'id': 'heizen', 'group': 'Becken 1'}],
        'deletes': ['heizstab'],
    })
    assert app.extensions['machineroom'].saved == 1


def test_apply_creates_alert_node(client, users, bus, app):
    # exercises apply_config_diff's own build_node() call (creates path),
    # not just api_create_node's direct route - Alert must be creatable
    # here too, with empty conditions/receives
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-alert', 'type': 'Alert', 'name': 'Neuer Alarm',
            'fields': {'port': '', 'repeat': 3600},
        }],
    })
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()

    alert_id = data['id_map']['tmp-alert']
    assert alert_id == 'neueralarm'
    new_node = bus.get_node(alert_id)
    assert new_node is not None
    assert new_node.conditions == set()
    assert new_node.receives == []

#!/usr/bin/env python3
""" Tests for Step 12: /api/node-types/ and /api/nodes/ (POST/PUT/DELETE),
    the backend part of the new /config graph editor.
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
    db.create_user(users_db, 'viewer1', 'viewerPass1', role='viewer')
    db.create_user(users_db, 'operator1', 'operatorPass1', role='operator')
    db.create_user(users_db, 'admin1', 'adminPass123', role='admin')


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


# --- GET /api/node-types/ ---------------------------------------------


def test_node_types_unauthenticated_succeeds_as_anonymous_viewer(client):
    resp = client.get('/api/node-types/')
    assert resp.status_code == HTTPStatus.OK


def test_node_types_lists_creatable_types(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/api/node-types/')
    assert resp.status_code == HTTPStatus.OK

    schema = resp.get_json()
    assert 'AnalogInput' in schema
    assert 'MinimumCtrl' in schema
    assert schema['MinimumCtrl']['receives'] == 'single'
    # Alert is intentionally excluded (complex 'conditions')
    assert 'Alert' not in schema


# --- POST /api/nodes/ ---------------------------------------------------


def test_create_node_requires_admin(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.post('/api/nodes/', json={
        'type': 'AnalogInput', 'name': 'Luft',
        'fields': {'port': '', 'unit': '°C'},
    })
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_create_analog_input_and_wire_to_controller(client, users, bus):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/nodes/', json={
        'type': 'AnalogInput', 'name': 'Luft',
        'fields': {'port': '', 'unit': '°C', 'initval': 20.0},
        'pos_x': 10, 'pos_y': 20,
    })
    assert resp.status_code == HTTPStatus.CREATED
    data = resp.get_json()
    assert data['type'] == 'AnalogInput'
    assert data['pos_x'] == 10
    assert data['pos_y'] == 20

    new_node = bus.get_node('luft')
    assert new_node is not None
    assert new_node.unit == '°C'

    # now rewire the existing controller to receive from the new sensor
    # instead (MinimumCtrl only accepts a single 'receives' source)
    resp = client.put('/api/nodes/heizen', json={'receives': ['luft']})
    assert resp.status_code == HTTPStatus.OK
    assert bus.get_node('heizen').receives == ['luft']


def test_create_node_unknown_type_returns_400(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/nodes/', json={'type': 'NoSuchType', 'name': 'X'})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_create_node_rejects_alert_type(client, users):
    # Alert isn't in NODE_TYPE_SCHEMA (excluded on purpose)
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/nodes/', json={'type': 'Alert', 'name': 'X'})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_create_node_duplicate_name_returns_400(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/nodes/', json={
        'type': 'AnalogInput', 'name': 'Wasser',  # already exists
        'fields': {'unit': '°C'},
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_create_node_missing_required_field_returns_400(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/nodes/', json={
        'type': 'MinimumCtrl', 'name': 'NeuerCtrl', 'receives': ['wasser'],
        'fields': {},  # 'setpoint' is required
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_create_node_unknown_receives_returns_400(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/nodes/', json={
        'type': 'MinimumCtrl', 'name': 'NeuerCtrl', 'receives': ['doesnotexist'],
        'fields': {'setpoint': 25.0},
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_create_node_too_many_receives_for_single_returns_400(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/nodes/', json={
        'type': 'MinimumCtrl', 'name': 'NeuerCtrl', 'receives': ['wasser', 'heizen'],
        'fields': {'setpoint': 25.0},
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_create_node_persists_topology(client, users, app):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/nodes/', json={
        'type': 'AnalogInput', 'name': 'Luft', 'fields': {'unit': '°C'},
    })
    assert app.extensions['machineroom'].saved == 1


# --- PUT /api/nodes/<id> ------------------------------------------------


def test_update_node_requires_admin(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.put('/api/nodes/heizen', json={'fields': {'setpoint': 26.0}})
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_update_node_fields(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    resp = client.put('/api/nodes/heizen', json={'fields': {'setpoint': 27.0}})
    assert resp.status_code == HTTPStatus.OK
    assert bus.get_node('heizen').setpoint == 27.0


def test_update_node_group_and_position(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    resp = client.put('/api/nodes/heizen', json={'group': 'Becken 1', 'pos_x': 5, 'pos_y': 6})
    assert resp.status_code == HTTPStatus.OK
    node = bus.get_node('heizen')
    assert node.group == 'Becken 1'
    assert node.pos_x == 5
    assert node.pos_y == 6


def test_update_node_unknown_returns_404(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.put('/api/nodes/doesnotexist', json={'group': 'x'})
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_update_node_rejects_cycle(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    # heizstab receives from heizen; making heizen receive from heizstab
    # would create a 2-node cycle
    resp = client.put('/api/nodes/heizen', json={'receives': ['heizstab']})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('heizen').receives == ['wasser']


def test_update_node_rejects_self_reference(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    resp = client.put('/api/nodes/heizen', json={'receives': ['heizen']})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_update_node_rejects_unknown_field(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.put('/api/nodes/heizen', json={'fields': {'nope': 1}})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_update_node_alert_fields_rejected(client, users):
    # Alert has no NODE_TYPE_SCHEMA entry, so field/receives edits are refused,
    # but group/position must still work
    _login(client, 'admin1', 'adminPass123')
    resp = client.put('/api/nodes/warnungen', json={'fields': {'repeat': 10}})
    assert resp.status_code == HTTPStatus.BAD_REQUEST

    resp = client.put('/api/nodes/warnungen', json={'group': 'Alerts'})
    assert resp.status_code == HTTPStatus.OK


# --- DELETE /api/nodes/<id> --------------------------------------------


def test_delete_node_requires_admin(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.delete('/api/nodes/heizstab')
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_delete_node_unknown_returns_404(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.delete('/api/nodes/doesnotexist')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_delete_leaf_node(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    resp = client.delete('/api/nodes/heizstab')
    assert resp.status_code == HTTPStatus.NO_CONTENT
    assert bus.get_node('heizstab') is None


def test_delete_referenced_node_cleans_dangling_reference(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    resp = client.delete('/api/nodes/wasser')
    assert resp.status_code == HTTPStatus.NO_CONTENT
    assert bus.get_node('wasser') is None
    # 'heizen' listened to 'wasser' - reference must be cleaned, not dangling
    assert 'wasser' not in bus.get_node('heizen').receives


def test_delete_node_persists_topology(client, users, app):
    _login(client, 'admin1', 'adminPass123')
    client.delete('/api/nodes/heizstab')
    assert app.extensions['machineroom'].saved == 1

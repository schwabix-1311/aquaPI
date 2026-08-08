#!/usr/bin/env python3
""" Tests for Step 11: /api/nodes/<id>/settings (GET/PUT), the backend
    part of the new /settings page with generic input widgets.
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


# --- GET /api/nodes/<id>/settings ------------------------------------------


def test_get_settings_unauthenticated_returns_401(client):
    resp = client.get('/api/nodes/heizen/settings')
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


def test_get_settings_unknown_node_returns_404(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/api/nodes/doesnotexist/settings')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_get_settings_viewer_can_read(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/api/nodes/heizen/settings')
    assert resp.status_code == HTTPStatus.OK

    settings = resp.get_json()
    by_key = {entry['key']: entry for entry in settings if entry['key']}
    assert 'setpoint' in by_key
    assert by_key['setpoint']['value'] == 24.0
    assert by_key['setpoint']['attrs']['type'] == 'number'
    assert by_key['setpoint']['editable'] is True

    assert 'hysteresis' in by_key
    assert by_key['hysteresis']['value'] == 0.5

    # every returned entry must be marked editable, since ControllerNode
    # deliberately doesn't inherit the read-only 'Receives' entry
    assert all(entry['editable'] for entry in settings)


def test_get_settings_readonly_entry_is_marked_non_editable(client, users):
    # SwitchDevice/DeviceNode chains up to BusListener.get_settings(),
    # which DOES add the read-only 'Receives' entry (key=None)
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/api/nodes/heizstab/settings')
    assert resp.status_code == HTTPStatus.OK

    settings = resp.get_json()
    readonly = [entry for entry in settings if entry['key'] is None]
    assert len(readonly) == 1
    assert readonly[0]['editable'] is False


# --- PUT /api/nodes/<id>/settings ------------------------------------------


def test_put_settings_requires_operator_or_admin(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.put('/api/nodes/heizen/settings', json={'setpoint': 26.0})
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_put_settings_operator_can_update(client, users, bus):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.put('/api/nodes/heizen/settings', json={'setpoint': 26.0})
    assert resp.status_code == HTTPStatus.OK

    ctrl = bus.get_node('heizen')
    assert ctrl.setpoint == 26.0

    settings = resp.get_json()
    by_key = {entry['key']: entry for entry in settings if entry['key']}
    assert by_key['setpoint']['value'] == 26.0


def test_put_settings_admin_can_update(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    resp = client.put('/api/nodes/heizen/settings', json={'hysteresis': 1.0})
    assert resp.status_code == HTTPStatus.OK
    assert bus.get_node('heizen').hysteresis == 1.0


def test_put_settings_persists_topology(client, users, app):
    _login(client, 'operator1', 'operatorPass1')
    client.put('/api/nodes/heizen/settings', json={'setpoint': 26.0})
    assert app.extensions['machineroom'].saved == 1


def test_put_settings_unknown_node_returns_404(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.put('/api/nodes/doesnotexist/settings', json={'setpoint': 1.0})
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_put_settings_rejects_non_object_body(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.put('/api/nodes/heizen/settings', json=[1, 2, 3])
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_put_settings_rejects_unknown_key(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.put('/api/nodes/heizen/settings', json={'not_a_setting': 1})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_put_settings_rejects_readonly_receives_key(client, users):
    _login(client, 'operator1', 'operatorPass1')
    # 'Receives' has key=None, so it can never be addressed by body key
    resp = client.put('/api/nodes/heizen/settings', json={'None': 'x'})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_put_settings_rejects_value_below_minimum(client, users, bus):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.put('/api/nodes/heizen/settings', json={'hysteresis': -1.0})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    # node must remain unchanged
    assert bus.get_node('heizen').hysteresis == 0.5


def test_put_settings_rejects_value_above_maximum(client, users, bus):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.put('/api/nodes/heizen/settings', json={'hysteresis': 999.0})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('heizen').hysteresis == 0.5


def test_put_settings_rejects_non_numeric_value(client, users, bus):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.put('/api/nodes/heizen/settings', json={'setpoint': 'not-a-number'})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('heizen').setpoint == 24.0

#!/usr/bin/env python3
""" Tests for Step 23: the audit log (aquaPi/db.py's audit_log table
    and functions, plus the resulting entries created by the existing
    config/setpoint/user-management write routes and the admin-only
    GET /api/audit-log endpoint).
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
def users_db_path(app):
    return db.get_users_db_path(app.config['INSTANCE_PATH'])


@pytest.fixture
def users(users_db_path):
    db.create_user(users_db_path, 'operator1', 'operatorPass1', role='operator')
    db.create_user(users_db_path, 'admin1', 'adminPass123', role='admin')


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


# --- db.py unit tests ----------------------------------------------------

def test_add_and_list_audit_log_entry(users_db_path):
    db.add_audit_log_entry(users_db_path, None, 'admin1', 'create_node', 'wasser',
                           {'type': 'AnalogInput'})
    result = db.list_audit_log(users_db_path)
    assert result['total'] == 1
    entry = result['entries'][0]
    assert entry['username'] == 'admin1'
    assert entry['action'] == 'create_node'
    assert entry['target'] == 'wasser'
    assert entry['details'] == {'type': 'AnalogInput'}
    assert entry['timestamp']


def test_list_audit_log_pagination(users_db_path):
    for i in range(5):
        db.add_audit_log_entry(users_db_path, None, 'admin1', 'create_node', f'node{i}')

    page1 = db.list_audit_log(users_db_path, limit=2, offset=0)
    assert page1['total'] == 5
    assert len(page1['entries']) == 2
    # newest first
    assert page1['entries'][0]['target'] == 'node4'

    page2 = db.list_audit_log(users_db_path, limit=2, offset=2)
    assert page2['entries'][0]['target'] == 'node2'


def test_list_audit_log_filters_by_action_and_username(users_db_path):
    # user_id=None is used here (rather than a real user row) since this
    # test only exercises the action/username filtering logic, not the
    # users(id) foreign key relationship
    db.add_audit_log_entry(users_db_path, None, 'admin1', 'create_node', 'a')
    db.add_audit_log_entry(users_db_path, None, 'admin1', 'delete_node', 'a')
    db.add_audit_log_entry(users_db_path, None, 'admin2', 'create_node', 'b')

    by_action = db.list_audit_log(users_db_path, action='create_node')
    assert by_action['total'] == 2

    by_user = db.list_audit_log(users_db_path, username='admin2')
    assert by_user['total'] == 1
    assert by_user['entries'][0]['target'] == 'b'


def test_add_audit_log_entry_never_raises_on_bad_path():
    # a path in a non-existent directory can't be opened -
    # add_audit_log_entry must swallow the error rather than propagate it
    db.add_audit_log_entry('/nonexistent-dir/x.sqlite', None, 'someone', 'noop')


# --- integration: existing write routes create audit entries -----------

def test_node_create_delete_creates_audit_entries(client, users, users_db_path, bus):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/nodes/', json={
        'type': 'AnalogInput', 'name': 'Luft', 'fields': {'unit': '°C'},
    })
    assert resp.status_code == HTTPStatus.CREATED

    resp = client.delete('/api/nodes/luft')
    assert resp.status_code == HTTPStatus.NO_CONTENT

    result = db.list_audit_log(users_db_path)
    actions = [e['action'] for e in result['entries']]
    assert 'create_node' in actions
    assert 'delete_node' in actions
    create_entry = next(e for e in result['entries'] if e['action'] == 'create_node')
    assert create_entry['target'] == 'luft'
    assert create_entry['username'] == 'admin1'


def test_setpoint_change_creates_audit_entry(client, users, users_db_path):
    _login(client, 'admin1', 'adminPass123')

    resp = client.put('/api/nodes/heizen/settings', json={'setpoint': 25.0})
    assert resp.status_code == HTTPStatus.OK

    result = db.list_audit_log(users_db_path)
    entry = next(e for e in result['entries'] if e['action'] == 'update_settings')
    assert entry['target'] == 'heizen'
    assert entry['details']['fields'] == ['setpoint']


def test_config_apply_creates_audit_entry(client, users, users_db_path):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-1', 'type': 'AnalogInput', 'name': 'Luft',
            'fields': {'unit': '°C'},
        }],
    })
    assert resp.status_code == HTTPStatus.OK

    result = db.list_audit_log(users_db_path)
    entry = next(e for e in result['entries'] if e['action'] == 'apply_config_diff')
    assert entry['details']['creates'] == 1


def test_user_management_creates_audit_entries(client, users, users_db_path):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/users/', json={
        'username': 'newbie', 'password': 'newbiePass1', 'role': 'viewer',
    })
    assert resp.status_code == HTTPStatus.CREATED
    new_id = resp.get_json()['id']

    resp = client.put(f'/api/users/{new_id}', json={'role': 'operator'})
    assert resp.status_code == HTTPStatus.OK

    resp = client.delete(f'/api/users/{new_id}')
    assert resp.status_code == HTTPStatus.NO_CONTENT

    result = db.list_audit_log(users_db_path)
    actions = [e['action'] for e in result['entries']]
    assert 'create_user' in actions
    assert 'update_user_role' in actions
    assert 'delete_user' in actions


# --- GET /api/audit-log endpoint ----------------------------------------

def test_audit_log_endpoint_requires_admin(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.get('/api/audit-log')
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_audit_log_endpoint_returns_entries(client, users, users_db_path):
    _login(client, 'admin1', 'adminPass123')

    client.post('/api/nodes/', json={
        'type': 'AnalogInput', 'name': 'Luft', 'fields': {'unit': '°C'},
    })

    resp = client.get('/api/audit-log')
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()
    assert data['total'] >= 1
    assert any(e['action'] == 'create_node' for e in data['entries'])


def test_audit_log_endpoint_pagination_and_filter(client, users, users_db_path):
    _login(client, 'admin1', 'adminPass123')

    for name in ('A', 'B', 'C'):
        client.post('/api/nodes/', json={
            'type': 'AnalogInput', 'name': name, 'fields': {'unit': '°C'},
        })

    resp = client.get('/api/audit-log?limit=2&offset=0')
    data = resp.get_json()
    assert len(data['entries']) == 2
    assert data['total'] == 3

    resp = client.get('/api/audit-log?action=create_node')
    data = resp.get_json()
    assert data['total'] == 3
    assert all(e['action'] == 'create_node' for e in data['entries'])


def test_audit_log_endpoint_rejects_bad_pagination(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.get('/api/audit-log?limit=abc')
    assert resp.status_code == HTTPStatus.BAD_REQUEST

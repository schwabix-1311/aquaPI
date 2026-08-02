#!/usr/bin/env python3
""" Tests for Step 8: user-specific dashboards and the 'group' node
    property.
    - aquaPi/db.py: dashboards table (get_dashboard/set_dashboard)
    - aquaPi/api.py: GET/PUT /api/dashboard/
    - aquaPi/machineroom/msg_bus.py: BusNode.group persists across
      __getstate__/__setstate__ (and thus through the SQLite topology)
"""

import os
from http import HTTPStatus

import pytest
from flask import Flask

import aquaPi
from aquaPi import auth, db, api
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.in_nodes import AnalogInput
from aquaPi.machineroom.ctrl_nodes import MinimumCtrl


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')


# --- aquaPi/db.py: dashboards table --------------------------------------


@pytest.fixture
def users_db_path(tmp_path):
    return str(tmp_path / 'users.sqlite')


def test_get_dashboard_default_is_empty_list(users_db_path):
    user_id = db.create_user(users_db_path, 'alice', 'pwd12345', role='viewer')
    assert db.get_dashboard(users_db_path, user_id) == []


def test_set_and_get_dashboard(users_db_path):
    user_id = db.create_user(users_db_path, 'bob', 'pwd12345', role='viewer')
    layout = [{'controller_id': 'heizen', 'group': 'Becken 1', 'position': 0, 'visible': True}]

    db.set_dashboard(users_db_path, user_id, layout)
    assert db.get_dashboard(users_db_path, user_id) == layout


def test_set_dashboard_overwrites(users_db_path):
    user_id = db.create_user(users_db_path, 'carol', 'pwd12345', role='viewer')
    db.set_dashboard(users_db_path, user_id, [{'controller_id': 'a'}])
    db.set_dashboard(users_db_path, user_id, [{'controller_id': 'b'}])
    assert db.get_dashboard(users_db_path, user_id) == [{'controller_id': 'b'}]


def test_dashboards_are_per_user(users_db_path):
    u1 = db.create_user(users_db_path, 'dave', 'pwd12345', role='viewer')
    u2 = db.create_user(users_db_path, 'erin', 'pwd12345', role='viewer')

    db.set_dashboard(users_db_path, u1, [{'controller_id': 'dave-widget'}])
    db.set_dashboard(users_db_path, u2, [{'controller_id': 'erin-widget'}])

    assert db.get_dashboard(users_db_path, u1) == [{'controller_id': 'dave-widget'}]
    assert db.get_dashboard(users_db_path, u2) == [{'controller_id': 'erin-widget'}]


def test_dashboard_cascades_on_user_delete(users_db_path):
    user_id = db.create_user(users_db_path, 'frank', 'pwd12345', role='viewer')
    db.set_dashboard(users_db_path, user_id, [{'controller_id': 'x'}])

    conn = db.get_users_connection(users_db_path)
    try:
        with conn:
            conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    finally:
        conn.close()

    # dashboard row is gone too (ON DELETE CASCADE) -> falls back to default
    assert db.get_dashboard(users_db_path, user_id) == []


# --- BusNode.group persists across (de-)serialization --------------------


def test_node_group_defaults_to_empty_string():
    node = AnalogInput('Wasser', '', 25.0, '°C')
    assert node.group == ''
    assert node.__getstate__()['group'] == ''


def test_node_group_roundtrips_through_getstate_setstate():
    node = AnalogInput('Wasser', '', 25.0, '°C')
    node.group = 'Becken 1'
    state = node.__getstate__()
    assert state['group'] == 'Becken 1'

    restored = AnalogInput.__new__(AnalogInput)
    restored.__setstate__(state)
    # AnalogInput/BusListener don't restore 'group' themselves (they call
    # their own __init__ instead of super().__setstate__()) - this
    # mirrors the central restoration done in db.py._deserialize_node
    restored.group = state.get('group', '')
    assert restored.group == 'Becken 1'


def test_node_group_persists_through_sqlite_topology(tmp_path):
    db_path = str(tmp_path / 'topo.sqlite')

    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.group = 'Becken 1'
    sensor.plugin(bus)

    ctrl = MinimumCtrl('Heizen', sensor.id, setpoint=24.0, hysteresis=0.5)
    ctrl.group = 'Becken 1'
    ctrl.plugin(bus)

    db.save_topology(bus, db_path)
    bus.teardown()

    bus2 = db.load_topology(db_path)
    try:
        groups = {node.name: node.group for node in bus2.nodes}
        assert groups == {'Wasser': 'Becken 1', 'Heizen': 'Becken 1'}
    finally:
        bus2.teardown()


def test_node_group_defaults_to_empty_after_reload_when_unset(tmp_path):
    db_path = str(tmp_path / 'topo.sqlite')

    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    db.save_topology(bus, db_path)
    bus.teardown()

    bus2 = db.load_topology(db_path)
    try:
        node = bus2.get_node(sensor.id)
        assert node.group == ''
    finally:
        bus2.teardown()


# --- GET/PUT /api/dashboard/ ----------------------------------------------


@pytest.fixture
def app(tmp_path):
    app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
    app.config['INSTANCE_PATH'] = str(tmp_path)
    app.config['TESTING'] = True

    auth.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)

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
    db.create_user(users_db, 'viewer2', 'viewerPass1', role='viewer')


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


def test_get_dashboard_unauthenticated_returns_401(client):
    resp = client.get('/api/dashboard/')
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


def test_get_dashboard_default_empty(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/api/dashboard/')
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == []


def test_put_and_get_dashboard_roundtrip(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    layout = [{'controller_id': 'heizen', 'group': 'Becken 1', 'position': 0, 'visible': True}]

    resp = client.put('/api/dashboard/', json=layout)
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == layout

    resp = client.get('/api/dashboard/')
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == layout


def test_put_dashboard_rejects_non_array_body(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.put('/api/dashboard/', json={'not': 'a list'})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_dashboard_is_isolated_between_users(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    client.put('/api/dashboard/', json=[{'controller_id': 'viewer1-widget'}])
    client.get('/logout')

    _login(client, 'viewer2', 'viewerPass1')
    resp = client.get('/api/dashboard/')
    assert resp.get_json() == []

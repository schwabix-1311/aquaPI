#!/usr/bin/env python3
""" Tests for Step 13: node-combination templates and configuration
    snapshots on /config (aquaPi/db.py + the new routes in aquaPi/api.py).
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
    def __init__(self, bus: MsgBus, topo_db_path: str):
        self.bus = bus
        self.globals = {'BUS_TOPO': topo_db_path}
        self.saved = 0

    def save_nodes(self, container):
        self.saved += 1
        db.save_topology(container, self.globals['BUS_TOPO'])


@pytest.fixture
def app(tmp_path, bus):
    app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
    app.config['INSTANCE_PATH'] = str(tmp_path)
    app.config['TESTING'] = True

    auth.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)

    topo_db_path = str(tmp_path / 'topo.sqlite')
    db.save_topology(bus, topo_db_path)  # so the 'nodes' table starts populated
    app.extensions['machineroom'] = _FakeMachineRoom(bus, topo_db_path)

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


# --- templates: capture/list/get/delete ---------------------------------


def test_list_templates_allows_operator(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.get('/api/templates/')
    assert resp.status_code == HTTPStatus.OK


def test_list_templates_empty(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.get('/api/templates/')
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == []


def test_create_template_requires_admin(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.post('/api/templates/', json={
        'name': 'pH-Regelung', 'node_ids': ['wasser', 'heizen'],
    })
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_create_and_list_template(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/templates/', json={
        'name': 'pH-Regelung', 'descr': 'sensor + ctrl + out',
        'node_ids': ['wasser', 'heizen', 'heizstab'],
    })
    assert resp.status_code == HTTPStatus.CREATED
    data = resp.get_json()
    assert data['name'] == 'pH-Regelung'
    assert len(data['data']['nodes']) == 3

    resp = client.get('/api/templates/')
    assert resp.status_code == HTTPStatus.OK
    listing = resp.get_json()
    assert len(listing) == 1
    assert listing[0]['name'] == 'pH-Regelung'
    assert listing[0]['node_count'] == 3


def test_create_template_unknown_node_returns_400(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/templates/', json={
        'name': 'X', 'node_ids': ['doesnotexist'],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_create_template_rejects_alert_node(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/templates/', json={
        'name': 'X', 'node_ids': ['warnungen'],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_create_template_empty_node_ids_returns_400(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/templates/', json={'name': 'X', 'node_ids': []})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_get_template_unknown_returns_404(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.get('/api/templates/doesnotexist')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_get_template_allows_operator(client, users):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'X', 'node_ids': ['wasser']})
    client.get('/logout')

    _login(client, 'operator1', 'operatorPass1')
    resp = client.get('/api/templates/X')
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json()['name'] == 'X'


def test_delete_template(client, users):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'X', 'node_ids': ['wasser']})

    resp = client.delete('/api/templates/X')
    assert resp.status_code == HTTPStatus.NO_CONTENT

    resp = client.get('/api/templates/X')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_delete_template_unknown_returns_404(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.delete('/api/templates/doesnotexist')
    assert resp.status_code == HTTPStatus.NOT_FOUND


# --- templates: insert (id remapping, no collisions) --------------------


def test_insert_template_creates_new_ids_and_wiring(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={
        'name': 'pH-Regelung',
        'node_ids': ['wasser', 'heizen', 'heizstab'],
    })

    resp = client.post('/api/templates/pH-Regelung/insert')
    assert resp.status_code == HTTPStatus.CREATED
    new_nodes = resp.get_json()
    assert len(new_nodes) == 3

    # original nodes must be untouched
    assert bus.get_node('wasser') is not None
    assert bus.get_node('heizen') is not None
    assert bus.get_node('heizstab') is not None

    # new nodes got fresh, non-colliding ids (suffix ' (2)')
    new_ids = {n['id'] for n in new_nodes}
    assert 'wasser' not in new_ids
    assert 'heizen' not in new_ids
    assert 'heizstab' not in new_ids
    assert len(new_ids) == 3

    # internal wiring must have been remapped to the new ids, not the
    # original ones
    new_sensor_id = next(n['id'] for n in new_nodes if n['type'] == 'AnalogInput')
    new_ctrl = next(n for n in new_nodes if n['type'] == 'MinimumCtrl')
    new_out = next(n for n in new_nodes if n['type'] == 'SwitchDevice')
    assert new_ctrl['receives'] == [new_sensor_id]
    assert new_out['receives'] == [new_ctrl['id']]


def test_insert_template_with_hw_port_does_not_conflict(tmp_path):
    """ regression test: inserting a template containing an input/output
        node that owns a real (still in-use) hardware/driver port must
        not raise a 500 (DriverPortInuseError) - the copied node's port
        must be blanked out instead, since only one node may own a
        given port at a time.
    """
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Temperatur', 'DS1820 #1', 25.0, '°C')
    sensor.plugin(bus)
    try:
        app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
        app.config['INSTANCE_PATH'] = str(tmp_path)
        app.config['TESTING'] = True
        auth.init_app(app)
        app.register_blueprint(auth.bp)
        app.register_blueprint(api.bp)

        topo_db_path = str(tmp_path / 'topo.sqlite')
        db.save_topology(bus, topo_db_path)
        app.extensions['machineroom'] = _FakeMachineRoom(bus, topo_db_path)

        @app.route('/', endpoint='spa.spa')
        def spa_stub():
            return 'spa'

        users_db = db.get_users_db_path(str(tmp_path))
        db.create_user(users_db, 'admin1', 'adminPass123', role='admin')

        client = app.test_client()
        _login(client, 'admin1', 'adminPass123')

        resp = client.post('/api/templates/', json={
            'name': 'Sensor', 'node_ids': ['temperatur'],
        })
        assert resp.status_code == HTTPStatus.CREATED
        # the captured template must not carry the live, still-used port
        assert resp.get_json()['data']['nodes'][0]['state']['port'] == ''

        resp = client.post('/api/templates/Sensor/insert')
        assert resp.status_code == HTTPStatus.CREATED
        new_nodes = resp.get_json()
        assert len(new_nodes) == 1
        assert new_nodes[0]['port'] == ''

        # original node must still be untouched and still own its port
        assert bus.get_node('temperatur') is not None
        assert bus.get_node('temperatur').port == 'DS1820 #1'
    finally:
        bus.teardown()


def test_insert_template_twice_avoids_collision(client, users):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'X', 'node_ids': ['wasser']})

    resp1 = client.post('/api/templates/X/insert')
    resp2 = client.post('/api/templates/X/insert')
    assert resp1.status_code == HTTPStatus.CREATED
    assert resp2.status_code == HTTPStatus.CREATED

    id1 = resp1.get_json()[0]['id']
    id2 = resp2.get_json()[0]['id']
    assert id1 != id2


def test_insert_template_requires_admin(client, users):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'X', 'node_ids': ['wasser']})
    client.get('/logout')

    _login(client, 'operator1', 'operatorPass1')
    resp = client.post('/api/templates/X/insert')
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_insert_template_unknown_returns_404(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/templates/doesnotexist/insert')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_insert_template_persists_topology(client, users, app):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'X', 'node_ids': ['wasser']})
    saved_before = app.extensions['machineroom'].saved

    client.post('/api/templates/X/insert')
    assert app.extensions['machineroom'].saved == saved_before + 1


# --- snapshots: save/list/get/delete ------------------------------------


def test_list_snapshots_allows_operator(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.get('/api/config/snapshots')
    assert resp.status_code == HTTPStatus.OK


def test_create_and_list_snapshot(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/config/snapshots', json={'name': 'backup1'})
    assert resp.status_code == HTTPStatus.CREATED
    data = resp.get_json()
    assert data['name'] == 'backup1'
    assert len(data['data']) == 4  # wasser, heizen, heizstab, warnungen
    assert isinstance(data['data'][0]['params'], dict)  # single-encoded, not a JSON string

    resp = client.get('/api/config/snapshots')
    assert resp.status_code == HTTPStatus.OK
    listing = resp.get_json()
    assert len(listing) == 1
    assert listing[0]['name'] == 'backup1'


def test_create_snapshot_empty_name_returns_400(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/config/snapshots', json={'name': ''})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_get_snapshot_unknown_returns_404(client, users):
    # there is no GET /api/config/snapshots/<name> route (only list +
    # restore), so verify the 404 via the restore route instead
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/config/snapshots/doesnotexist/restore')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_delete_snapshot(client, users):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/config/snapshots', json={'name': 'backup1'})

    resp = client.delete('/api/config/snapshots/backup1')
    assert resp.status_code == HTTPStatus.NO_CONTENT

    resp = client.get('/api/config/snapshots')
    assert resp.get_json() == []


def test_delete_snapshot_unknown_returns_404(client, users):
    _login(client, 'admin1', 'adminPass123')
    resp = client.delete('/api/config/snapshots/doesnotexist')
    assert resp.status_code == HTTPStatus.NOT_FOUND


# --- snapshots: restore (identity round-trip) ---------------------------


def test_restore_snapshot_round_trip(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/config/snapshots', json={'name': 'backup1'})

    # change the live topology: add a node and change a setpoint
    client.post('/api/nodes/', json={
        'type': 'AnalogInput', 'name': 'Luft', 'fields': {'unit': '°C'},
    })
    client.put('/api/nodes/heizen', json={'fields': {'setpoint': 99.0}})
    assert bus.get_node('luft') is not None
    assert bus.get_node('heizen').setpoint == 99.0

    resp = client.post('/api/config/snapshots/backup1/restore')
    assert resp.status_code == HTTPStatus.OK
    restored = resp.get_json()
    assert len(restored) == 4

    ids = {n['id'] for n in restored}
    assert ids == {'wasser', 'heizen', 'heizstab', 'warnungen'}
    assert 'luft' not in ids

    heizen = next(n for n in restored if n['id'] == 'heizen')
    assert heizen['setpoint'] == 24.0


def test_restore_snapshot_requires_admin(client, users):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/config/snapshots', json={'name': 'backup1'})
    client.get('/logout')

    _login(client, 'operator1', 'operatorPass1')
    resp = client.post('/api/config/snapshots/backup1/restore')
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_restore_snapshot_persists_topology(client, users, app):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/config/snapshots', json={'name': 'backup1'})
    saved_before = app.extensions['machineroom'].saved

    client.post('/api/config/snapshots/backup1/restore')
    assert app.extensions['machineroom'].saved == saved_before + 1


def test_restore_snapshot_skips_conflicting_port_instead_of_emptying_bus():
    """ regression test: a snapshot containing two nodes that (e.g. due
        to a previous bug, or a manually edited export) claim the same
        hardware/driver port used to raise an uncaught
        DriverPortInuseError, which aborted restore_snapshot_into_bus()
        *after* it had already torn down the live bus - leaving it
        permanently empty (GET /api/nodes/ then 500s forever). The
        conflicting node must now be skipped instead, so the rest of
        the topology (and therefore the live bus) survives the restore.
    """
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Temperatur', 'DS1820 #1', 25.0, '°C')
    sensor.plugin(bus)
    try:
        snapshot_rows = [
            {'id': 'temperatur', 'type': 'AnalogInput',
             'params': dict(sensor.__getstate__(), name='Temperatur')},
            {'id': 'temperatur-2', 'type': 'AnalogInput',
             'params': dict(sensor.__getstate__(), name='Temperatur 2')},
        ]

        # must not raise, even though both entries claim 'DS1820 #1'
        db.restore_snapshot_into_bus(bus, snapshot_rows)

        # at least the first node must have survived the restore -
        # the bus must not be left permanently empty
        assert len(bus.nodes) == 1
        assert bus.get_node('temperatur') is not None
        assert bus.get_node('temperatur').port == 'DS1820 #1'
    finally:
        bus.teardown()

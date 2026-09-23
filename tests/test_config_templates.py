#!/usr/bin/env python3
""" Tests for Step 13: node-combination templates and configuration
    snapshots on /config (aquaPi/db.py + the new routes in aquaPi/api.py).
"""

import json
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
    def __init__(self, bus: MsgBus, wiring_db_path: str):
        self.bus = bus
        self.globals = {'BUS_WIRING': wiring_db_path}
        self.saved = 0

    def save_nodes(self, container):
        self.saved += 1
        db.save_wiring(container, self.globals['BUS_WIRING'])


@pytest.fixture
def app(tmp_path, bus):
    app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
    app.config['INSTANCE_PATH'] = str(tmp_path)
    app.config['TESTING'] = True

    auth.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)

    wiring_db_path = str(tmp_path / 'wiring.sqlite')
    db.save_wiring(bus, wiring_db_path)  # so the 'nodes' table starts populated
    app.extensions['machineroom'] = _FakeMachineRoom(bus, wiring_db_path)

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


def _existing_from_bus(bus):
    """ build the '/api/templates/<name>/insert' 'existing' payload a
        real frontend draft would send - id + position of every node it
        currently has, live or itself still unsaved - so template-insert
        collision/overlap avoidance has something to avoid.
    """
    return [{'id': n.id, 'pos_x': getattr(n, 'pos_x', 0.0) or 0.0,
             'pos_y': getattr(n, 'pos_y', 0.0) or 0.0} for n in bus.nodes]


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


# --- templates: predefined library vs user folder ---------------------


@pytest.fixture(autouse=True)
def template_lib(tmp_path, monkeypatch):
    """ redirect the predefined-template folder to an isolated, empty
        temp dir for EVERY test in this module, so exact-count/exact-list
        assertions stay valid no matter what aquaPi/templates_lib/ ships.
    """
    lib = tmp_path / 'templates_lib'
    lib.mkdir()
    monkeypatch.setattr(db, '_TEMPLATE_LIB_DIR', str(lib))
    return lib


def _write_lib_template(folder, name, descr='', nodes=()):
    with open(os.path.join(folder, f'{name}.json'), 'w', encoding='utf-8') as f:
        json.dump({'name': name, 'descr': descr,
                   'data': {'nodes': list(nodes)}}, f)


def test_user_template_is_written_to_the_instance_folder(client, users, tmp_path, template_lib):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'My Setup', 'node_ids': ['wasser']})

    files = os.listdir(tmp_path / 'templates')
    assert len(files) == 1 and files[0].endswith('.json')

    listing = client.get('/api/templates/').get_json()
    assert listing[0]['name'] == 'My Setup'
    assert listing[0]['source'] == 'user'


def test_predefined_template_is_listed_and_read_only(client, users, template_lib):
    _write_lib_template(template_lib, 'Temp Control', descr='sensor+ctrl', nodes=[{}, {}])

    _login(client, 'admin1', 'adminPass123')

    listing = client.get('/api/templates/').get_json()
    entry = next(t for t in listing if t['name'] == 'Temp Control')
    assert entry['source'] == 'predefined'
    assert entry['node_count'] == 2

    assert client.get('/api/templates/Temp Control').status_code == HTTPStatus.OK

    resp = client.delete('/api/templates/Temp Control')
    assert resp.status_code == HTTPStatus.FORBIDDEN
    # still there
    assert any(t['name'] == 'Temp Control'
               for t in client.get('/api/templates/').get_json())


def test_user_template_shadows_predefined_of_same_name(client, users, template_lib):
    _write_lib_template(template_lib, 'pH-Regelung', descr='shipped', nodes=[{}])

    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={
        'name': 'pH-Regelung', 'descr': 'mine',
        'node_ids': ['wasser', 'heizen'],
    })

    listing = client.get('/api/templates/').get_json()
    entry = next(t for t in listing if t['name'] == 'pH-Regelung')
    assert entry['source'] == 'user'
    assert entry['node_count'] == 2          # the user's version
    assert client.get('/api/templates/pH-Regelung').get_json()['descr'] == 'mine'

    # deleting the user copy brings the predefined one back
    assert client.delete('/api/templates/pH-Regelung').status_code == HTTPStatus.NO_CONTENT
    entry = next(t for t in client.get('/api/templates/').get_json()
                 if t['name'] == 'pH-Regelung')
    assert entry['source'] == 'predefined'
    assert entry['node_count'] == 1


def test_templates_survive_a_wiring_db_deletion(client, users, tmp_path, template_lib):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'Keep Me', 'node_ids': ['wasser']})

    os.remove(tmp_path / 'wiring.sqlite')  # what `./run -r` does

    listing = client.get('/api/templates/').get_json()
    assert [t['name'] for t in listing] == ['Keep Me']


# --- templates: i18n of predefined ones ------------------------------


def _write_i18n_lib_template(folder, bus):
    """ a 'temp-heater' predefined template built from the real bus nodes
        'wasser' + 'heizen', wrapped in an i18n block keyed on those ids.
    """
    tmpl = {
        'id': 'temp-heater',
        'i18n': {
            'de': {'name': 'Temperatur', 'descr': 'Regelung',
                   'nodes': {'wasser': 'Wasser DE', 'heizen': 'Heizen DE'}},
            'en': {'name': 'Temperature', 'descr': 'control',
                   'nodes': {'wasser': 'Water', 'heizen': 'Heater ctrl'}},
        },
        'data': db.capture_node_template(bus, ['wasser', 'heizen']),
    }
    with open(os.path.join(folder, 'temp-heater.json'), 'w', encoding='utf-8') as f:
        json.dump(tmpl, f)


def test_predefined_template_name_follows_lang(client, users, bus, template_lib):
    _write_i18n_lib_template(template_lib, bus)
    _login(client, 'admin1', 'adminPass123')

    de = client.get('/api/templates/?lang=de').get_json()[0]
    en = client.get('/api/templates/?lang=en').get_json()[0]
    assert de['id'] == en['id'] == 'temp-heater'
    assert (de['name'], en['name']) == ('Temperatur', 'Temperature')
    assert (de['descr'], en['descr']) == ('Regelung', 'control')
    assert de['node_count'] == 2


def test_get_template_localises_node_names(client, users, bus, template_lib):
    _write_i18n_lib_template(template_lib, bus)
    _login(client, 'admin1', 'adminPass123')

    en = client.get('/api/templates/temp-heater?lang=en').get_json()
    assert sorted(n['state']['name'] for n in en['data']['nodes']) \
        == ['Heater ctrl', 'Water']

    de = client.get('/api/templates/temp-heater?lang=de').get_json()
    assert sorted(n['state']['name'] for n in de['data']['nodes']) \
        == ['Heizen DE', 'Wasser DE']


def test_unknown_lang_falls_back_to_de(client, users, bus, template_lib):
    _write_i18n_lib_template(template_lib, bus)
    _login(client, 'admin1', 'adminPass123')

    fr = client.get('/api/templates/?lang=fr').get_json()[0]
    assert fr['name'] == 'Temperatur'   # de fallback


def test_user_template_is_unaffected_by_lang(client, users, template_lib):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'Meine Vorlage', 'node_ids': ['wasser']})

    for lang in ('de', 'en', 'fr'):
        entry = client.get(f'/api/templates/?lang={lang}').get_json()[0]
        assert entry['name'] == 'Meine Vorlage'
        assert entry['id'] == 'Meine Vorlage'


def test_insert_localises_the_new_node_names(client, users, bus, template_lib):
    _write_i18n_lib_template(template_lib, bus)
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/templates/temp-heater/insert?lang=en')
    assert resp.status_code == HTTPStatus.OK
    assert sorted(n['name'] for n in resp.get_json()) == ['Heater ctrl', 'Water']


# --- templates: insert (id remapping, no collisions) --------------------


def test_insert_template_creates_new_ids_and_wiring(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={
        'name': 'pH-Regelung',
        'node_ids': ['wasser', 'heizen', 'heizstab'],
    })

    resp = client.post('/api/templates/pH-Regelung/insert',
                       json={'existing': _existing_from_bus(bus)})
    assert resp.status_code == HTTPStatus.OK
    new_nodes = resp.get_json()
    assert len(new_nodes) == 3

    # original nodes must be untouched
    assert bus.get_node('wasser') is not None
    assert bus.get_node('heizen') is not None
    assert bus.get_node('heizstab') is not None

    # new nodes got fresh, non-colliding ids (suffix ' (2)') - and were
    # only ever built, never actually attached to the live bus
    new_ids = {n['id'] for n in new_nodes}
    assert 'wasser' not in new_ids
    assert 'heizen' not in new_ids
    assert 'heizstab' not in new_ids
    assert len(new_ids) == 3
    assert len(bus.nodes) == 4
    for new_id in new_ids:
        assert bus.get_node(new_id) is None

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

        wiring_db_path = str(tmp_path / 'wiring.sqlite')
        db.save_wiring(bus, wiring_db_path)
        app.extensions['machineroom'] = _FakeMachineRoom(bus, wiring_db_path)

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

        resp = client.post('/api/templates/Sensor/insert',
                           json={'existing': _existing_from_bus(bus)})
        assert resp.status_code == HTTPStatus.OK
        new_nodes = resp.get_json()
        assert len(new_nodes) == 1
        assert new_nodes[0]['port'] == ''

        # original node must still be untouched and still own its port -
        # and the preview must not have attached anything to the bus
        assert bus.get_node('temperatur') is not None
        assert bus.get_node('temperatur').port == 'DS1820 #1'
        assert len(bus.nodes) == 1
    finally:
        bus.teardown()


def test_insert_template_twice_avoids_collision(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'X', 'node_ids': ['wasser']})

    resp1 = client.post('/api/templates/X/insert', json={'existing': _existing_from_bus(bus)})
    assert resp1.status_code == HTTPStatus.OK
    id1 = resp1.get_json()[0]['id']

    # nothing persisted, so a second insert only avoids colliding with
    # the first if the caller's draft (now also holding resp1's still-
    # unsaved node) is passed as 'existing' again - exactly what the
    # frontend does when inserting a second template into the same draft
    existing2 = _existing_from_bus(bus) + [
        {'id': n['id'], 'pos_x': n.get('pos_x', 0.0), 'pos_y': n.get('pos_y', 0.0)}
        for n in resp1.get_json()
    ]
    resp2 = client.post('/api/templates/X/insert', json={'existing': existing2})
    assert resp2.status_code == HTTPStatus.OK
    id2 = resp2.get_json()[0]['id']

    assert id1 != id2


def test_instantiate_template_remaps_alert_condition_node_id_on_collision(bus):
    """ regression: instantiate_template() remapped 'receives' through its
        id_map on a name/id collision but not Alert.conditions[].node_id -
        since Alert.receives is re-derived FROM conditions on deserialize
        (overwriting the remapped 'receives'), a colliding insert left the
        alert silently watching the wrong, pre-existing node.

        capture_node_template() (the UI "save selected nodes as template"
        path) refuses Alert nodes outright, so this builds the template
        dict directly, the way a hand-authored predefined template
        (aquaPi/templates_lib/*.json) would - that's the path an Alert
        template actually ships through.
    """
    # a self-contained sensor + Alert pair, same ids/names as the bus
    # fixture's own 'wasser'/'warnungen' -> forces an id collision on insert
    tmp_bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(tmp_bus)
    alert = Alert('Warnungen', AlertAbove(sensor.id, 30.0), '')
    alert.plugin(tmp_bus)
    data = {'nodes': [
        {'id': sensor.id, 'type': type(sensor).__name__, 'state': db.serialize_node(sensor)},
        {'id': alert.id, 'type': type(alert).__name__, 'state': db.serialize_node(alert)},
    ]}
    tmp_bus.teardown()

    new_nodes = db.instantiate_template(data, {n.id for n in bus.nodes}, [])
    new_sensor = next(n for n in new_nodes if isinstance(n, AnalogInput))
    new_alert = next(n for n in new_nodes if isinstance(n, Alert))
    assert new_sensor.id != 'wasser'

    assert new_alert.receives == [new_sensor.id]
    assert [c.node_id for c in new_alert.conditions] == [new_sensor.id]


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


def test_insert_template_does_not_persist_wiring(client, users, app, bus):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/templates/', json={'name': 'X', 'node_ids': ['wasser']})
    saved_before = app.extensions['machineroom'].saved
    nodes_before = len(bus.nodes)

    resp = client.post('/api/templates/X/insert', json={'existing': _existing_from_bus(bus)})
    assert resp.status_code == HTTPStatus.OK
    assert app.extensions['machineroom'].saved == saved_before
    assert len(bus.nodes) == nodes_before


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


def test_restore_snapshot_preview_reflects_snapshot_not_live_bus(client, users, bus):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/config/snapshots', json={'name': 'backup1'})

    # change the live wiring: add a node and change a setpoint
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

    # the preview reflects the snapshot as captured, unaffected by the
    # live mutations made since
    ids = {n['id'] for n in restored}
    assert ids == {'wasser', 'heizen', 'heizstab', 'warnungen'}
    assert 'luft' not in ids

    heizen = next(n for n in restored if n['id'] == 'heizen')
    assert heizen['setpoint'] == 24.0

    # ...but it's only a preview - the live bus itself is untouched
    assert bus.get_node('luft') is not None
    assert bus.get_node('heizen').setpoint == 99.0


def test_restore_snapshot_requires_admin(client, users):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/config/snapshots', json={'name': 'backup1'})
    client.get('/logout')

    _login(client, 'operator1', 'operatorPass1')
    resp = client.post('/api/config/snapshots/backup1/restore')
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_restore_snapshot_does_not_persist_wiring(client, users, app):
    _login(client, 'admin1', 'adminPass123')
    client.post('/api/config/snapshots', json={'name': 'backup1'})
    saved_before = app.extensions['machineroom'].saved

    resp = client.post('/api/config/snapshots/backup1/restore')
    assert resp.status_code == HTTPStatus.OK
    assert app.extensions['machineroom'].saved == saved_before


def test_preview_snapshot_nodes_never_touches_ports():
    """ regression test: a snapshot containing two nodes that (e.g. due
        to a previous bug, or a manually edited export) claim the same
        hardware/driver port used to raise an uncaught
        DriverPortInuseError when the old restore_snapshot_into_bus()
        constructed/plugged them both into the live bus (port claiming
        happens eagerly in a node's own __init__/__setstate__, not just
        at plugin() time - see PortDriverMixin._apply_port()).
        preview_snapshot_nodes() never constructs real node objects at
        all (pure dict reshaping), so both nodes must come back intact,
        still carrying their (conflicting) port, with no exception
        raised and nothing claimed in the real IoRegistry.
    """
    sensor = AnalogInput('Temperatur', 'DS1820 #1', 25.0, '°C')
    try:
        snapshot_rows = [
            {'id': 'temperatur', 'type': 'AnalogInput',
             'params': dict(sensor.__getstate__(), name='Temperatur')},
            {'id': 'temperatur-2', 'type': 'AnalogInput',
             'params': dict(sensor.__getstate__(), name='Temperatur 2')},
        ]

        nodes, failures = db.preview_snapshot_nodes(snapshot_rows)

        assert failures == []
        assert len(nodes) == 2
        assert {n['port'] for n in nodes} == {'DS1820 #1'}
        assert {n['type'] for n in nodes} == {'AnalogInput'}
        assert {n['role'] for n in nodes} == {'IN_ENDP'}
    finally:
        sensor.port = ''

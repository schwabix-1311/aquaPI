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
from aquaPi.driver import create_io_registry, IoRegistry
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.in_nodes import AnalogInput
from aquaPi.machineroom.out_nodes import SwitchDevice
from aquaPi.machineroom.ctrl_nodes import MinimumCtrl
from aquaPi.machineroom.alert_nodes import Alert, AlertAbove


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')

# a valid, otherwise-arbitrary 2-point calibration (factor 1, offset 0) -
# ScaleAux.points is required with no default, so every create below needs
# one just to be a legal node, independent of whatever else the test checks
_CALIB_POINTS = [{'measured': 0.0, 'reference': 0.0}, {'measured': 1.0, 'reference': 1.0}]


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


@pytest.fixture
def bus():
    bus = MsgBus(threaded=False)
    # real ports, not '' - apply_config_diff now rejects a save that
    # leaves a port-having node with none set (see test_config_apply's
    # "missing required value" tests below), so a node this fixture
    # provides untouched must not itself violate that on every test
    sensor = AnalogInput('Wasser', 'DS1820 #1', 25.0, '°C')
    sensor.plugin(bus)

    ctrl = MinimumCtrl('Heizen', sensor.id, setpoint=24.0, hysteresis=0.5)
    ctrl.plugin(bus)

    out = SwitchDevice('Heizstab', ctrl.id, 'GPIO 13 out')
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
            'fields': {'unit': '°C', 'port': 'DS1820 #2'},
        }],
        'updates': [{'id': 'heizen', 'receives': ['tmp-1']}],
        'deletes': ['heizstab'],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
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
             'fields': {'unit': '°C', 'port': 'DS1820 #2'}},
            {'temp_id': 't-ctrl', 'type': 'MinimumCtrl', 'name': 'Luftregler',
             'receives': ['t-sensor'], 'fields': {'setpoint': 20.0}},
        ],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
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


def test_apply_creates_alert_node_with_conditions(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-a', 'type': 'Alert', 'name': 'Alarm',
            'fields': {'port': '', 'repeat': 3600, 'conditions': [
                {'class': 'AlertAbove', 'node_id': 'wasser', 'limit': 28.0, 'duration': 0},
            ]},
        }],
    })
    assert resp.status_code == HTTPStatus.OK
    node = bus.get_node('alarm')
    assert len(node.conditions) == 1
    assert node.receives == ['wasser']


def test_apply_creates_stddev_aux_node(client, users, bus, app):
    # exercises apply_config_diff's own build_node() call (creates path) -
    # NODE_FACTORY alone isn't enough for a type to be creatable via
    # /api/config/apply, build_node() has its own separate type_name
    # dispatch that must also know the type, or it falls through to an
    # untranslated ValueError even though node_type_schema (built from
    # NODE_FACTORY) already listed the type as valid
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-sd', 'type': 'StdDevAux', 'name': 'Schwankung',
            'receives': ['wasser'], 'fields': {'window': 1800},
        }],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    data = resp.get_json()

    node_id = data['id_map']['tmp-sd']
    assert node_id == 'schwankung'
    node = bus.get_node(node_id)
    assert node is not None
    assert node.receives == ['wasser']
    assert node.window == 1800


def test_apply_updates_alert_conditions_and_derives_receives(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')
    resp = client.post('/api/config/apply', json={
        'updates': [{'id': 'warnungen', 'fields': {'conditions': [
            {'class': 'AlertBelow', 'node_id': 'wasser', 'limit': 5.0, 'duration': 2},
        ]}}],
    })
    assert resp.status_code == HTTPStatus.OK
    node = bus.get_node('warnungen')
    assert [type(c).__name__ for c in node.conditions] == ['AlertBelow']
    assert node.receives == ['wasser']


def test_apply_rejects_alert_condition_on_string_source(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')
    # create a STRING-typed TextInput, then try to watch it from an Alert
    resp = client.post('/api/config/apply', json={
        'creates': [
            {'temp_id': 't-txt', 'type': 'TextInput', 'name': 'Notiz', 'fields': {'port': ''}},
            {'temp_id': 't-al', 'type': 'Alert', 'name': 'Alarm', 'fields': {
                'port': '', 'repeat': 3600,
                'conditions': [{'class': 'AlertAbove', 'node_id': 't-txt', 'limit': 1.0}]}},
        ],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('alarm') is None
    assert bus.get_node('notiz') is None


def test_apply_delete_source_with_stale_receives_in_listener_update(client, users, bus, app):
    """ regression: deleting a node while a surviving listener's update
        payload still lists the just-deleted id in its 'receives' (the
        /wiring editor marks that listener dirty for an unrelated pos
        change) must NOT abort the whole diff - the dangling ref is
        dropped, exactly as prune_dangling_references() does on apply.
        'heizen' is single-cardinality, so alongside the dangling ref
        the update also rewires it to a fresh replacement sensor in the
        same diff - otherwise it would end up with zero receives, which
        is itself now rejected (see the missing-required-value tests).
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 't-new', 'type': 'AnalogInput', 'name': 'Ersatz',
                     'fields': {'unit': '°C', 'port': 'DS1820 #2'}}],
        'deletes': ['wasser'],
        'updates': [{'id': 'heizen', 'pos_x': 42, 'receives': ['wasser', 't-new']}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node('wasser') is None
    assert bus.get_node('heizen').receives == ['ersatz']
    assert bus.get_node('heizen').pos_x == 42
    assert app.extensions['machineroom'].saved == 1


def test_apply_delete_source_keeps_listener_other_receives(client, users, bus, app):
    """ a multi-input listener that also names the deleted id in its
        update payload keeps its *other*, still-valid wires.
    """
    _login(client, 'admin1', 'adminPass123')

    # a History listening to both 'wasser' and 'heizen'
    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-h', 'type': 'History', 'name': 'Verlauf',
            'receives': ['wasser', 'heizen'], 'fields': {'capacity': 24 * 60 * 60},
        }],
    })
    assert resp.status_code == HTTPStatus.OK
    hist_id = resp.get_json()['id_map']['tmp-h']
    assert set(bus.get_node(hist_id).receives) == {'wasser', 'heizen'}

    resp = client.post('/api/config/apply', json={
        # 'heizen' is untouched by this diff's own updates, but its only
        # source ('wasser') is being deleted - left as-is it would end up
        # with zero receives too (now itself rejected), so rewire it to a
        # fresh replacement in the same diff, same as the dangling-ref test
        # above.
        'creates': [{'temp_id': 't-new', 'type': 'AnalogInput', 'name': 'Ersatz2',
                     'fields': {'unit': '°C', 'port': 'DS1820 #2'}}],
        'deletes': ['wasser'],
        'updates': [
            {'id': 'heizen', 'receives': ['t-new']},
            {'id': hist_id, 'pos_x': 7, 'receives': ['wasser', 'heizen']},
        ],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node('wasser') is None
    assert bus.get_node(hist_id).receives == ['heizen']


def test_apply_delete_source_frees_its_port_despite_stale_receives(client, users, bus, app):
    """ symptom 1: because the diff is atomic, a validation abort (from
        the stale-receives case above) also meant node.pullout() never
        ran and the deleted node's hardware port stayed held. With the
        dangling ref tolerated, the delete goes through and the port is
        released.
    """
    _login(client, 'admin1', 'adminPass123')
    port = 'ADC #1 in 0'

    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-s', 'type': 'AnalogInput', 'name': 'Becken',
            'fields': {'unit': '°C', 'port': port},
        }, {
            'temp_id': 'tmp-h', 'type': 'History', 'name': 'Verlauf2',
            'receives': ['tmp-s'], 'fields': {'capacity': 24 * 60 * 60},
        }],
    })
    assert resp.status_code == HTTPStatus.OK
    id_map = resp.get_json()['id_map']
    sensor_id, hist_id = id_map['tmp-s'], id_map['tmp-h']
    assert IoRegistry._map[port].used == 1

    resp = client.post('/api/config/apply', json={
        'deletes': [sensor_id],
        # 'heizen' alongside the now-dangling sensor_id: History is
        # multi-cardinality, and this keeps hist_id from ending up with
        # zero receives (itself now rejected) once the stale ref drops.
        'updates': [{'id': hist_id, 'pos_x': 5, 'receives': [sensor_id, 'heizen']}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node(sensor_id) is None
    assert IoRegistry._map[port].used == 0


def test_apply_update_keeps_nodes_own_in_use_port(client, users, bus, app):
    """ get_node_type_schema()'s 'port' select lists only *free* ports, but
        the /wiring editor resubmits the whole fields object on any edit -
        so an unrelated change to a node that holds a port must not be
        rejected just because its own (now in-use) port isn't in the free
        list. merge_live_select_options() unions it back in.
    """
    _login(client, 'admin1', 'adminPass123')
    port = 'ADC #1 in 0'

    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-s', 'type': 'AnalogInput', 'name': 'Becken',
            'fields': {'unit': '°C', 'port': port},
        }],
    })
    assert resp.status_code == HTTPStatus.OK
    sensor_id = resp.get_json()['id_map']['tmp-s']
    port_field = next(f for f in db.get_node_type_schema()['AnalogInput']['fields']
                      if f['key'] == 'port')
    assert port not in port_field['attrs']['options']  # in use -> not offered

    # an edit that changes 'interval' but resubmits the held port verbatim
    resp = client.post('/api/config/apply', json={
        'updates': [{'id': sensor_id,
                     'fields': {'unit': '°C', 'port': port, 'interval': 30.0}}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node(sensor_id).interval == 30.0
    assert bus.get_node(sensor_id).port == port

    # a genuinely bogus port is still rejected
    resp = client.post('/api/config/apply', json={
        'updates': [{'id': sensor_id,
                     'fields': {'unit': '°C', 'port': 'ADC #9 in 9', 'interval': 30.0}}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_apply_reuses_a_port_freed_in_the_same_diff_only_for_its_function(client, users, bus, app):
    """ deleting a Bout node in a diff frees its GPIO-out port; another
        node in the *same* diff may take it - but only a node of the same
        function (_schema_allowing_ports is gated on attrs.allPorts), not
        e.g. an AnalogInput.
    """
    _login(client, 'admin1', 'adminPass123')
    port = 'GPIO 12 out'

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'sw', 'type': 'SwitchDevice', 'name': 'Relais',
                     'receives': ['heizen'], 'fields': {'port': port}}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    sw_id = resp.get_json()['id_map']['sw']

    # delete it and, in one diff, hand the freed Bout port to a new Bout node
    resp = client.post('/api/config/apply', json={
        'deletes': [sw_id],
        'creates': [{'temp_id': 'sw2', 'type': 'SwitchDevice', 'name': 'Relais2',
                     'receives': ['heizen'], 'fields': {'port': port}}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node(resp.get_json()['id_map']['sw2']).port == port

    # ...but an AnalogInput may not take that Bout port even though it is
    # "freed" in the diff - it is not in AnalogInput's allPorts
    sw2_id = resp.get_json()['id_map']['sw2']
    resp = client.post('/api/config/apply', json={
        'deletes': [sw2_id],
        'creates': [{'temp_id': 'ai', 'type': 'AnalogInput', 'name': 'Sensor',
                     'fields': {'unit': '°C', 'port': port}}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_apply_rejects_two_nodes_claiming_the_same_port(client, users, bus, app):
    """ each 'port' select only offers *free* ports, so two draft nodes can
        independently pick the same one. That must be a clean 400 in the
        validation phase - not a DriverPortInuseError 500 half-way through
        applying the diff.
    """
    _login(client, 'admin1', 'adminPass123')
    port = 'ADC #1 in 0'

    resp = client.post('/api/config/apply', json={
        'creates': [
            {'temp_id': 'a', 'type': 'AnalogInput', 'name': 'SensorA',
             'fields': {'unit': '°C', 'port': port}},
            {'temp_id': 'b', 'type': 'AnalogInput', 'name': 'SensorB',
             'fields': {'unit': '°C', 'port': port}},
        ],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert port in resp.get_json()['error']
    assert bus.get_node('sensora') is None and bus.get_node('sensorb') is None
    assert IoRegistry._map[port].used == 0  # nothing was applied

    # the same collision between an existing node and a new one
    client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'a', 'type': 'AnalogInput', 'name': 'SensorA',
                     'fields': {'unit': '°C', 'port': port}}],
    })
    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'c', 'type': 'AnalogInput', 'name': 'SensorC',
                     'fields': {'unit': '°C', 'port': port}}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_apply_rejects_dual_use_pin_conflict(client, users, bus, app):
    """ a dual-use pin: 'PWM 1' also reserves 'GPIO 19 in/out' (its deps),
        so a second node taking 'GPIO 19 out' directly collides - even
        though the two port *names* differ.
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [
            {'temp_id': 'p', 'type': 'AnalogDevice', 'name': 'Dimmer',
             'receives': ['heizen'], 'fields': {'port': 'PWM 1'}},
            {'temp_id': 'g', 'type': 'SwitchDevice', 'name': 'Relais',
             'receives': ['heizen'], 'fields': {'port': 'GPIO 19 out'}},
        ],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert 'GPIO 19 out' in resp.get_json()['error']
    assert bus.get_node('dimmer') is None and bus.get_node('relais') is None


def test_apply_allows_shared_bus_deps(client, users, bus, app):
    """ two 'ADC #1 in N' channels share the same I2C-bus pins as deps -
        that is NOT a conflict (IoRegistry refcounts shared deps).
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [
            {'temp_id': 'a', 'type': 'AnalogInput', 'name': 'SensorA',
             'fields': {'unit': '°C', 'port': 'ADC #1 in 0'}},
            {'temp_id': 'b', 'type': 'AnalogInput', 'name': 'SensorB',
             'fields': {'unit': '°C', 'port': 'ADC #1 in 1'}},
        ],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node('sensora').port == 'ADC #1 in 0'
    assert bus.get_node('sensorb').port == 'ADC #1 in 1'


def test_apply_reuses_a_freed_dual_use_pin_in_the_same_diff(client, users, bus, app):
    """ deleting a 'PWM 1' node frees the dual-use pin it also reserved
        as a dep ('GPIO 19 out'), not just the port name 'PWM 1' itself -
        a plain-GPIO node may take that pin over in the very same diff.
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'ad', 'type': 'AnalogDevice', 'name': 'Dimmer2',
                     'receives': ['heizen'], 'fields': {'port': 'PWM 1'}}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    ad_id = resp.get_json()['id_map']['ad']

    resp = client.post('/api/config/apply', json={
        'deletes': [ad_id],
        'creates': [{'temp_id': 'sw', 'type': 'SwitchDevice', 'name': 'Relais3',
                     'receives': ['heizen'], 'fields': {'port': 'GPIO 19 out'}}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node(resp.get_json()['id_map']['sw']).port == 'GPIO 19 out'


def test_apply_frees_a_pwm_port_when_its_dep_pin_owner_is_deleted_in_the_same_diff(
        client, users, bus, app):
    """ item #8 (reverse of the dual-use-pin test above): a plain-GPIO
        node squatting on a PWM's dep pin hides that PWM port. Deleting
        the GPIO node and creating a new PWM node in the very same diff
        must unblock the PWM port too - not just the reverse direction.
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'sw', 'type': 'SwitchDevice', 'name': 'Luefter',
                     'receives': ['heizen'], 'fields': {'port': 'GPIO 19 out'}}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    sw_id = resp.get_json()['id_map']['sw']

    resp = client.post('/api/config/apply', json={
        'deletes': [sw_id],
        'creates': [{'temp_id': 'ad', 'type': 'AnalogDevice', 'name': 'Dimmer3',
                     'receives': ['heizen'], 'fields': {'port': 'PWM 1'}}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node(resp.get_json()['id_map']['ad']).port == 'PWM 1'


def test_apply_does_not_over_free_a_shared_bus_pin(client, users, bus, app):
    """ deleting one of two ADC channels sharing the I2C-bus pins must NOT
        free those pins for a third node - the surviving channel still
        needs them (unlike the dual-use-pin case above, where nobody else
        was left holding the freed pin).
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [
            {'temp_id': 'a', 'type': 'AnalogInput', 'name': 'SensorC',
             'fields': {'unit': '°C', 'port': 'ADC #1 in 0'}},
            {'temp_id': 'b', 'type': 'AnalogInput', 'name': 'SensorD',
             'fields': {'unit': '°C', 'port': 'ADC #1 in 1'}},
        ],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    a_id = resp.get_json()['id_map']['a']

    resp = client.post('/api/config/apply', json={
        'deletes': [a_id],
        'creates': [{'temp_id': 'sw', 'type': 'SwitchDevice', 'name': 'Relais5',
                     'receives': ['heizen'], 'fields': {'port': 'GPIO 2 out'}}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('relais5') is None
    assert bus.get_node('sensord') is not None   # SensorD (and its bus claim) survived


def test_apply_swaps_two_nodes_ports(client, users, bus, app):
    """ two updates that swap ports A<->B have a valid end state; the apply
        phase releases both before reclaiming so it doesn't transiently
        double-claim and 500.
    """
    _login(client, 'admin1', 'adminPass123')
    pa, pb = 'ADC #1 in 0', 'ADC #1 in 1'

    resp = client.post('/api/config/apply', json={
        'creates': [
            {'temp_id': 'a', 'type': 'AnalogInput', 'name': 'SensorA',
             'fields': {'unit': '°C', 'port': pa}},
            {'temp_id': 'b', 'type': 'AnalogInput', 'name': 'SensorB',
             'fields': {'unit': '°C', 'port': pb}},
        ],
    })
    assert resp.status_code == HTTPStatus.OK
    ids = resp.get_json()['id_map']

    resp = client.post('/api/config/apply', json={
        'updates': [
            {'id': ids['a'], 'fields': {'unit': '°C', 'port': pb}},
            {'id': ids['b'], 'fields': {'unit': '°C', 'port': pa}},
        ],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node(ids['a']).port == pb
    assert bus.get_node(ids['b']).port == pa


def test_apply_rejects_string_source_wiring(client, users, bus, app):
    """ a STRING-typed source (the Alert 'warnungen') cannot be wired as
        a 'receives' input - every consumer treats the value numerically
        or stores it in a numeric column. Rejected for an update...
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'updates': [{'id': 'heizen', 'receives': ['warnungen']}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert 'STRING' in resp.get_json()['error']
    assert bus.get_node('heizen').receives == ['wasser']

    # ...and for a create
    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-h', 'type': 'History', 'name': 'Verlauf',
            'receives': ['warnungen'], 'fields': {'capacity': 24 * 60 * 60},
        }],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('verlauf') is None

    # a normal numeric source still wires fine
    resp = client.post('/api/config/apply', json={
        'creates': [{
            'temp_id': 'tmp-h2', 'type': 'History', 'name': 'Verlauf2',
            'receives': ['wasser'], 'fields': {'capacity': 24 * 60 * 60},
        }],
    })
    assert resp.status_code == HTTPStatus.OK


# --- missing-required-value save gate (port/receives) + its i18n key/items ---


def test_apply_rejects_a_new_node_with_no_port(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'a', 'type': 'AnalogInput', 'name': 'Sensor',
                     'fields': {'unit': '°C', 'port': ''}}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    body = resp.get_json()
    assert "'Sensor'" in body['error'] and 'inputPort' in body['error']
    assert body['error_items'] == [
        {'key': 'missingValue', 'params': {'node': 'Sensor', 'fieldLabel': 'inputPort'}},
    ]
    assert bus.get_node('sensor') is None


def test_apply_rejects_clearing_an_existing_nodes_port(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'updates': [{'id': 'heizstab', 'fields': {'port': ''}}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    body = resp.get_json()
    assert body['error_items'] == [
        {'key': 'missingValue', 'params': {'node': 'Heizstab', 'fieldLabel': 'outputPort'}},
    ]
    assert bus.get_node('heizstab').port == 'GPIO 13 out'   # unchanged, nothing applied


def test_apply_rejects_a_listener_with_no_receives(client, users, bus, app):
    """ ScaleAux (and any other listener type) needs at least one input
        to do anything - the concrete case that prompted this: a
        template-inserted ScaleAux ships with receives=[] by design.
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'a', 'type': 'ScaleAux', 'name': 'Skalierung',
                     'fields': {'points': _CALIB_POINTS}}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    body = resp.get_json()
    assert body['error_items'] == [
        {'key': 'notConnected', 'params': {'node': 'Skalierung'}},
    ]
    assert 'not' in body['error'] or 'missing' in body['error']
    assert bus.get_node('skalierung') is None


def test_apply_rejects_an_untouched_live_node_left_unconnected(client, users, bus, app):
    """ the whole-draft scan isn't limited to nodes THIS diff touches -
        an already-broken node (e.g. from a template insert, which
        bypasses apply_config_diff entirely) blocks the next, otherwise
        unrelated save too, until it's fixed.
    """
    _login(client, 'admin1', 'adminPass123')

    stray = MinimumCtrl('Stray', 'wasser', setpoint=1.0)
    stray.plugin(bus)
    stray.receives = []   # simulate an already-broken, disconnected node

    resp = client.post('/api/config/apply', json={
        'updates': [{'id': 'heizstab', 'pos_x': 99}],   # harmless, unrelated
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    body = resp.get_json()
    assert body['error_items'] == [
        {'key': 'notConnected', 'params': {'node': 'Stray'}},
    ]
    assert bus.get_node('heizstab').pos_x != 99   # nothing was applied

    stray.pullout()


def test_apply_reports_multiple_missing_values_in_one_diff(client, users, bus, app):
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [
            {'temp_id': 'a', 'type': 'AnalogInput', 'name': 'SensorX',
             'fields': {'unit': '°C', 'port': ''}},
            {'temp_id': 'b', 'type': 'ScaleAux', 'name': 'SkalierungX',
             'fields': {'points': _CALIB_POINTS}},
        ],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    body = resp.get_json()
    assert len(body['error_items']) == 2
    keys = {(item['key'], item['params']['node']) for item in body['error_items']}
    assert keys == {('missingValue', 'SensorX'), ('notConnected', 'SkalierungX')}


def test_apply_localizes_an_unexpected_post_validation_failure(client, users, bus, app,
                                                                monkeypatch):
    """ apply_config_diff's own validation is meant to catch everything
        before the bus is touched - if something still raises a plain
        ValueError/KeyError/DriverError past that (e.g. a NODE_FACTORY
        entry with no matching build_node() branch, the exact bug that
        prompted this test), api.py wraps it instead of a bare 500, and
        that wrapper must carry error_key/error_params so the frontend
        can localize it rather than showing raw English (see
        wiringErrors.js's documented fallback contract).
    """
    _login(client, 'admin1', 'adminPass123')

    def _boom(bus, diff, validate_fields):
        raise ValueError("Unknown or non-creatable node type: 'Bogus'")

    monkeypatch.setattr(db, 'apply_config_diff', _boom)

    resp = client.post('/api/config/apply', json={'updates': []})
    assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    body = resp.get_json()
    assert body['error_key'] == 'applyFailedUnexpected'
    assert body['error_params'] == {'detail': "Unknown or non-creatable node type: 'Bogus'"}


def test_apply_leaves_bus_untouched_when_a_later_create_fails(client, users, bus, app,
                                                               monkeypatch):
    """ regression test for the exact live-bus corruption this reordering
        prevents: build every create before mutating any existing node's
        receives/fields, so a create that fails past validation (build_node()
        raising for an unanticipated reason) can't leave an update from the
        same diff already committed on the live bus with no way back - the
        in-memory corruption an actual missing NODE_FACTORY/build_node()
        branch caused in production before this fix.
    """
    _login(client, 'admin1', 'adminPass123')

    real_build_node = db.build_node

    def _flaky_build_node(type_name, name, receives, fields):
        if type_name == 'AvgAux':
            raise ValueError('boom')
        return real_build_node(type_name, name, receives, fields)

    monkeypatch.setattr(db, 'build_node', _flaky_build_node)

    resp = client.post('/api/config/apply', json={
        'updates': [{'id': 'warnungen', 'fields': {'conditions': [
            {'class': 'AlertBelow', 'node_id': 'wasser', 'limit': 5.0, 'duration': 2},
        ]}}],
        'creates': [{'temp_id': 'a', 'type': 'AvgAux', 'name': 'Mittel',
                     'receives': ['wasser'], 'fields': {'unfair_avg': 0}}],
    })
    assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    node = bus.get_node('warnungen')
    assert [type(c).__name__ for c in node.conditions] == ['AlertAbove']   # untouched
    assert bus.get_node('mittel') is None   # never created


def test_apply_allows_alert_with_no_port_and_no_conditions(client, users, bus, app):
    """ both of Alert's exemptions hold: no escalation channel and no
        watched conditions are both legitimate (dashboard-only alert).
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'a', 'type': 'Alert', 'name': 'StillerAlarm',
                     'fields': {'port': '', 'repeat': 3600}}],
    })
    assert resp.status_code == HTTPStatus.OK, resp.get_json()
    assert bus.get_node('stilleralarm') is not None


def test_apply_still_rejects_missing_setpoint(client, users, bus, app):
    """ no regression from routing 'setpoint' through the same generic
        missing-required-value mechanism as port/receives.
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'a', 'type': 'MinimumCtrl', 'name': 'CtrlOhneSollwert',
                     'receives': ['wasser'], 'fields': {}}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert bus.get_node('ctrlohnesollwert') is None


def test_apply_error_key_and_params_for_a_plain_and_a_parametrized_message(
        client, users, bus, app):
    """ locks in the error_key/error_params contract (not just error_items)
        for the two other message shapes: no params, and one param.
    """
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'updates': [{'id': 'heizen', 'receives': ['heizstab']}],   # heizstab receives from heizen
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    body = resp.get_json()
    assert body['error_key'] == 'cycleDetected'
    assert body['error_params'] is None

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'a', 'type': 'AnalogInput', 'name': 'Heizstab',
                     'fields': {'unit': '°C', 'port': 'DS1820 #2'}}],
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    body = resp.get_json()
    assert body['error_key'] == 'duplicateName'
    assert body['error_params'] == {'name': 'Heizstab'}


# --- calibration history logging parity with PUT /api/nodes/<id>/settings ---
# (see tests/test_history_export.py's own "PUT .../settings triggers
# calibration logging" section for that endpoint's coverage)


def test_apply_updates_scaleaux_logs_calibration_event(client, users, bus, app, monkeypatch):
    recorded = []
    monkeypatch.setattr(db, 'log_calibration_event',
                        lambda node_id, old_points, new_points:
                            recorded.append((node_id, old_points, new_points)))
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'creates': [{'temp_id': 'a', 'type': 'ScaleAux', 'name': 'Skalierung',
                     'receives': ['wasser'],
                     'fields': {'unit': 'pH', 'points': _CALIB_POINTS}}],
    })
    assert resp.status_code == HTTPStatus.OK
    node_id = bus.get_node('skalierung').id
    assert recorded == []   # a create is not a calibration "change"

    new_points = [{'measured': 0.0, 'reference': 1.5}, {'measured': 1.0, 'reference': 2.5}]
    resp = client.post('/api/config/apply', json={
        'updates': [{'id': node_id, 'fields': {'points': new_points}}],
    })
    assert resp.status_code == HTTPStatus.OK
    assert recorded == [(node_id, _CALIB_POINTS, new_points)]


def test_apply_updates_non_calibration_field_does_not_log(client, users, bus, app, monkeypatch):
    recorded = []
    monkeypatch.setattr(db, 'log_calibration_event',
                        lambda node_id, old_points, new_points:
                            recorded.append((node_id, old_points, new_points)))
    _login(client, 'admin1', 'adminPass123')

    resp = client.post('/api/config/apply', json={
        'updates': [{'id': 'heizen', 'fields': {'setpoint': 26.0}}],
    })
    assert resp.status_code == HTTPStatus.OK
    assert recorded == []

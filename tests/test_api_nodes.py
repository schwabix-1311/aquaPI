#!/usr/bin/env python3
""" Tests for Step 9: REST API responses without jsonpickle.
    - aquaPi/api.py: GET /api/nodes/ and GET /api/nodes/<id> return plain
      JSON (via json.dumps + db.serialize_node), with no jsonpickle
      object-introspection artifacts (no 'py/object' keys etc.).
    - Alert.conditions (previously a set of custom AlertCond objects) is
      normalized to a list of plain dicts, reusing aquaPi/db.py's
      serialize_node()/_cond_to_dict(), the same logic used for SQLite
      persistence.
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


class _FakeMachineRoom:
    """ minimal stand-in for aquaPi.machineroom.MachineRoom, exposing
        only the .bus attribute that aquaPi/api.py's the_bus() reads
    """
    def __init__(self, bus: MsgBus):
        self.bus = bus


@pytest.fixture
def bus():
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.group = 'Becken 1'
    sensor.plugin(bus)

    ctrl = MinimumCtrl('Heizen', sensor.id, setpoint=24.0, hysteresis=0.5)
    ctrl.plugin(bus)

    alert = Alert('Warnung', AlertAbove(sensor.id, limit=30.0, duration=5), port='')
    alert.plugin(bus)

    yield bus
    bus.teardown()


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
def logged_in_client(app, client):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    db.create_user(users_db, 'viewer1', 'viewerPass1', role='viewer')
    client.post('/login', data={'username': 'viewer1', 'password': 'viewerPass1'})
    return client


# --- GET /api/nodes/ -------------------------------------------------------


def test_get_nodes_returns_plain_json_list(logged_in_client):
    resp = logged_in_client.get('/api/nodes/')
    assert resp.status_code == HTTPStatus.OK
    assert resp.mimetype == 'application/json'

    ids = resp.get_json()
    assert isinstance(ids, list)
    assert set(ids) == {'wasser', 'heizen', 'warnung'}
    # must be plain strings, no jsonpickle metadata anywhere in the body
    assert 'py/object' not in resp.get_data(as_text=True)


def test_get_nodes_unauthenticated_returns_401(client):
    resp = client.get('/api/nodes/')
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


# --- GET /api/nodes/<id> ----------------------------------------------------


def test_get_node_returns_plain_json_dict(logged_in_client):
    resp = logged_in_client.get('/api/nodes/wasser')
    assert resp.status_code == HTTPStatus.OK
    assert resp.mimetype == 'application/json'

    body = resp.get_json()
    assert body['result'] == 'SUCCESS'

    item = body['data']
    assert item['id'] == 'wasser'
    assert item['name'] == 'Wasser'
    assert item['type'] == 'AnalogInput'
    assert item['role'] == 'IN_ENDP'
    assert item['group'] == 'Becken 1'
    assert item['unit'] == '°C'

    # no jsonpickle object-introspection markers anywhere in the response
    raw = resp.get_data(as_text=True)
    assert 'py/object' not in raw
    assert 'py/id' not in raw

    # must be valid, plain json.loads-able (i.e. not jsonpickle-specific)
    reparsed = json.loads(raw)
    assert reparsed == body


def test_get_node_unknown_id_returns_404(logged_in_client):
    resp = logged_in_client.get('/api/nodes/doesnotexist')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_get_node_unauthenticated_returns_401(client):
    resp = client.get('/api/nodes/wasser')
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


# --- Alert.conditions serialization ----------------------------------------


def test_get_alert_node_conditions_are_plain_dicts(logged_in_client):
    resp = logged_in_client.get('/api/nodes/warnung')
    assert resp.status_code == HTTPStatus.OK

    item = resp.get_json()['data']
    assert item['type'] == 'Alert'
    assert item['role'] == 'ALERTS'

    conditions = item['conditions']
    assert isinstance(conditions, list)
    assert len(conditions) == 1
    cond = conditions[0]
    assert cond == {
        'class': 'AlertAbove',
        'node_id': 'wasser',
        'limit': 30.0,
        'duration': 5,
    }

    # a raw operator.ge/operator.le callable (AlertCond._cmp) must never
    # leak into the JSON response
    raw = resp.get_data(as_text=True)
    assert 'operator.ge' not in raw
    assert '_cmp' not in raw

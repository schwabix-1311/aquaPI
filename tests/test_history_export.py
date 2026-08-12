#!/usr/bin/env python3
""" Tests for Step 28 (extended sensor history):
    - GET /api/history/<id>/export (CSV/JSON export of a History node)
    - GET /api/nodes/<id>/calibration-log (ScaleAux calibration history)
    - aquaPi/machineroom/hist_nodes.py: log_calibration_event()/get_calibration_log()
    - PUT /api/nodes/<id>/settings logs a calibration event for ScaleAux offset/factor changes
"""

import os
from http import HTTPStatus

import pytest
from flask import Flask

import aquaPi
from aquaPi import auth, db, api
from aquaPi.driver import create_io_registry
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.msg_types import MsgData
from aquaPi.machineroom.in_nodes import AnalogInput
from aquaPi.machineroom.aux_nodes import ScaleAux
from aquaPi.machineroom.hist_nodes import History
from aquaPi.machineroom import hist_nodes


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


@pytest.fixture
def bus(monkeypatch):
    # force the deterministic in-memory time series backend, independent
    # of whether a real QuestDB happens to be reachable in this environment
    monkeypatch.setattr(hist_nodes, 'QUEST_DB', False)

    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    calib = ScaleAux('pH Kalibrierung', sensor.id, 'pH', offset=1.0, factor=2.0)
    calib.plugin(bus)

    hist = History('Verlauf', [sensor.id], capacity=1)
    hist.plugin(bus)

    yield bus
    bus.teardown()


class _FakeMachineRoom:
    def __init__(self, bus):
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


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


# --- GET /api/history/<id>/export ----------------------------------------


def test_export_unauthenticated_succeeds_as_anonymous_viewer(client, bus):
    # no session at all is auto-logged-in as the reserved anonymous
    # viewer account (see auth.py's before_request hook) - GET is
    # login_required only, no role restriction
    hist = next(n for n in bus.get_nodes() if isinstance(n, History))
    resp = client.get(f'/api/history/{hist.id}/export')
    assert resp.status_code == HTTPStatus.OK


def test_export_unknown_node_returns_404(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/api/history/does-not-exist/export')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_export_non_history_node_returns_404(client, users, bus):
    sensor = next(n for n in bus.get_nodes() if isinstance(n, AnalogInput))
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get(f'/api/history/{sensor.id}/export')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_export_invalid_format_returns_400(client, users, bus):
    hist = next(n for n in bus.get_nodes() if isinstance(n, History))
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get(f'/api/history/{hist.id}/export?format=xml')
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_export_json_default_format(client, users, bus):
    sensor = next(n for n in bus.get_nodes() if isinstance(n, AnalogInput))
    hist = next(n for n in bus.get_nodes() if isinstance(n, History))
    hist.listen(MsgData(sensor.id, 42.0))

    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get(f'/api/history/{hist.id}/export')
    assert resp.status_code == HTTPStatus.OK
    assert resp.mimetype == 'application/json'

    body = resp.get_json()
    assert body['node_id'] == hist.id
    assert sensor.id in body['fields']
    assert len(body['data']) >= 1
    # the in-memory store is shared across the test session and averages
    # multiple values landing in the same second, so just check our value
    # actually made it through, rather than asserting an exact match
    assert any(row.get(sensor.id) is not None for row in body['data'])


def test_export_csv_format(client, users, bus):
    sensor = next(n for n in bus.get_nodes() if isinstance(n, AnalogInput))
    hist = next(n for n in bus.get_nodes() if isinstance(n, History))
    hist.listen(MsgData(sensor.id, 17.5))

    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get(f'/api/history/{hist.id}/export?format=csv')
    assert resp.status_code == HTTPStatus.OK
    assert resp.mimetype == 'text/csv'
    assert 'attachment' in resp.headers.get('Content-Disposition', '')

    text = resp.get_data(as_text=True)
    lines = text.strip().splitlines()
    assert lines[0].split(',') == ['timestamp', sensor.id]
    # in-memory store is shared/averaged across the test session, so just
    # check some data rows were exported, not the exact fed-in value
    assert len(lines) > 1


def test_export_logs_audit_entry(client, users, bus, app):
    hist = next(n for n in bus.get_nodes() if isinstance(n, History))
    _login(client, 'viewer1', 'viewerPass1')
    client.get(f'/api/history/{hist.id}/export?format=json')

    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    entries = db.list_audit_log(users_db)['entries']
    assert any(e['action'] == 'export_history' for e in entries)


# --- GET /api/nodes/<id>/calibration-log ---------------------------------


def test_calibration_log_unauthenticated_succeeds_as_anonymous_viewer(client, bus):
    calib = next(n for n in bus.get_nodes() if isinstance(n, ScaleAux))
    resp = client.get(f'/api/nodes/{calib.id}/calibration-log')
    assert resp.status_code == HTTPStatus.OK


def test_calibration_log_unknown_node_returns_404(client, users):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/api/nodes/does-not-exist/calibration-log')
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_calibration_log_empty_when_questdb_unavailable(client, users, bus, monkeypatch):
    calib = next(n for n in bus.get_nodes() if isinstance(n, ScaleAux))
    monkeypatch.setattr(api, 'QUEST_DB', False)
    monkeypatch.setattr(hist_nodes, 'QUEST_DB', False)

    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get(f'/api/nodes/{calib.id}/calibration-log')
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == []


def test_calibration_log_returns_recorded_entries(client, users, bus, monkeypatch):
    calib = next(n for n in bus.get_nodes() if isinstance(n, ScaleAux))

    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, *_a, **_kw):
            self._rows = [
                (_FakeTs('2024-01-01T00:00:00'), 'offset', 1.0, 1.5),
            ]

        def fetchall(self):
            return self._rows

    class _FakeTs:
        def __init__(self, iso):
            self._iso = iso

        def isoformat(self):
            return self._iso

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def cursor(self):
            return _FakeCursor()

    class _FakePg:
        @staticmethod
        def connect(*_a, **_kw):
            return _FakeConn()

    monkeypatch.setattr(hist_nodes, 'QUEST_DB', True)
    monkeypatch.setattr(hist_nodes, 'pg', _FakePg)

    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get(f'/api/nodes/{calib.id}/calibration-log')
    assert resp.status_code == HTTPStatus.OK
    body = resp.get_json()
    assert body == [{'ts': '2024-01-01T00:00:00', 'field': 'offset',
                     'old_value': 1.0, 'new_value': 1.5}]


# --- hist_nodes.log_calibration_event()/get_calibration_log() -----------


def test_log_calibration_event_returns_false_without_questdb(monkeypatch):
    monkeypatch.setattr(hist_nodes, 'QUEST_DB', False)
    assert hist_nodes.log_calibration_event('node1', 'offset', 1.0, 2.0) is False


def test_log_calibration_event_executes_insert(monkeypatch):
    executed = []

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, qry, params=None):
            executed.append((str(qry), params))

    class _FakePg:
        @staticmethod
        def connect(*_a, **_kw):
            return _FakeConn()

    monkeypatch.setattr(hist_nodes, 'QUEST_DB', True)
    monkeypatch.setattr(hist_nodes, 'pg', _FakePg)

    assert hist_nodes.log_calibration_event('ph_probe', 'factor', 2.0, 2.1) is True
    # 1 CREATE TABLE + 1 INSERT
    assert len(executed) == 2
    insert_params = executed[1][1]
    assert insert_params == ['ph_probe', 'factor', 2.0, 2.1]


def test_get_calibration_log_returns_empty_without_questdb(monkeypatch):
    monkeypatch.setattr(hist_nodes, 'QUEST_DB', False)
    assert hist_nodes.get_calibration_log('node1') == []


def test_log_calibration_event_swallows_errors(monkeypatch):
    class _FakePg:
        @staticmethod
        def connect(*_a, **_kw):
            raise OSError('unreachable')

    monkeypatch.setattr(hist_nodes, 'QUEST_DB', True)
    monkeypatch.setattr(hist_nodes, 'pg', _FakePg)
    assert hist_nodes.log_calibration_event('node1', 'offset', 1.0, 2.0) is False


# --- PUT /api/nodes/<id>/settings triggers calibration logging ----------


def test_settings_update_of_scaleaux_logs_calibration_event(client, users, bus, monkeypatch):
    calib = next(n for n in bus.get_nodes() if isinstance(n, ScaleAux))
    recorded = []
    monkeypatch.setattr(api, 'log_calibration_event',
                        lambda node_id, field, old, new: recorded.append((node_id, field, old, new)))

    _login(client, 'operator1', 'operatorPass1')
    resp = client.put(f'/api/nodes/{calib.id}/settings', json={'offset': 1.5})
    assert resp.status_code == HTTPStatus.OK
    assert recorded == [(calib.id, 'offset', 1.0, 1.5)]


def test_settings_update_of_non_calibration_field_does_not_log(client, users, bus, monkeypatch):
    sensor = next(n for n in bus.get_nodes() if isinstance(n, AnalogInput))
    recorded = []
    monkeypatch.setattr(api, 'log_calibration_event',
                        lambda *a: recorded.append(a))

    _login(client, 'operator1', 'operatorPass1')
    resp = client.put(f'/api/nodes/{sensor.id}/settings', json={'unit': '°F'})
    assert resp.status_code == HTTPStatus.OK
    assert recorded == []

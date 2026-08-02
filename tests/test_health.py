#!/usr/bin/env python3
""" Tests for Step 25: unauthenticated GET /api/health endpoint and
    the graceful-degradation fix in aquaPi/driver/__init__.py's
    IoRegistry (a single misbehaving driver's find_ports() - e.g. a
    misconfigured Email/Telegram account - must not block the whole
    app from starting).
"""

import os
from http import HTTPStatus

import pytest
from flask import Flask

import aquaPi
from aquaPi import auth, db, api
from aquaPi.driver import IoRegistry, create_io_registry
from aquaPi.driver.base import Driver
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.in_nodes import AnalogInput
from aquaPi.machineroom.out_nodes import SwitchDevice
from aquaPi.machineroom.ctrl_nodes import MinimumCtrl
from aquaPi.machineroom import hist_nodes


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
    def __init__(self, bus):
        self.bus = bus
        self.globals = {}


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


# --- GET /api/health -------------------------------------------------

def test_health_does_not_require_login(client):
    resp = client.get('/api/health')
    assert resp.status_code == HTTPStatus.OK


def test_health_reports_expected_shape(client, bus):
    resp = client.get('/api/health')
    body = resp.get_json()

    assert body['status'] == 'ok'
    assert isinstance(body['timestamp'], float)
    assert body['mode'] in ('simulation', 'hardware')
    assert body['nodes']['active'] == len(bus.get_nodes())
    assert isinstance(body['questdb']['available'], bool)
    assert isinstance(body['questdb']['reachable'], bool)


def test_health_reachable_is_false_when_questdb_unavailable(client, monkeypatch):
    monkeypatch.setattr(api, 'QUEST_DB', False)
    resp = client.get('/api/health')
    body = resp.get_json()
    assert body['questdb']['available'] is False
    assert body['questdb']['reachable'] is False


def test_health_reports_zero_nodes_without_a_bus(app, client):
    app.extensions['machineroom'].bus = None
    resp = client.get('/api/health')
    body = resp.get_json()
    assert body['nodes']['active'] == 0


# --- check_questdb_reachable() -----------------------------------------

def test_check_questdb_reachable_false_when_driver_missing(monkeypatch):
    monkeypatch.setattr(hist_nodes, 'QUEST_DB', False)
    assert hist_nodes.check_questdb_reachable() is False


def test_check_questdb_reachable_false_on_connection_error(monkeypatch):
    class _FakePg:
        @staticmethod
        def connect(*_a, **_kw):
            raise OSError('no route to host')

    monkeypatch.setattr(hist_nodes, 'QUEST_DB', True)
    monkeypatch.setattr(hist_nodes, 'pg', _FakePg)
    assert hist_nodes.check_questdb_reachable() is False


def test_check_questdb_reachable_true_on_success(monkeypatch):
    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, *_a, **_kw):
            return None

    class _FakePg:
        @staticmethod
        def connect(*_a, **_kw):
            return _FakeConn()

    monkeypatch.setattr(hist_nodes, 'QUEST_DB', True)
    monkeypatch.setattr(hist_nodes, 'pg', _FakePg)
    assert hist_nodes.check_questdb_reachable() is True


# --- IoRegistry graceful degradation (Step 25) --------------------------

class _BrokenDriver(Driver):
    """ a fake driver whose find_ports() always fails, simulating a
        misconfigured Email/Telegram account that used to crash the
        whole app at startup
    """
    @staticmethod
    def find_ports():
        raise RuntimeError('simulated misconfiguration, e.g. bad SMTP login')


def test_io_registry_skips_a_broken_driver_without_raising(monkeypatch):
    # IoRegistry.__init__ discovers driver classes by scanning
    # sys.modules for anything under 'driver.' - register our fake
    # broken driver as if it were such a loaded driver module
    import sys
    import types

    fake_module = types.ModuleType('aquaPi.driver.fake_broken')
    fake_module.BrokenDriver = _BrokenDriver
    monkeypatch.setitem(sys.modules, 'aquaPi.driver.fake_broken', fake_module)

    # must not raise despite the broken driver
    IoRegistry()

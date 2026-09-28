#!/usr/bin/env python3
""" Shared pytest fixtures for the whole test suite (Step 29).

    Individual test files are free to keep their own, more specialized
    'app'/'client'/'_io_registry' fixtures (pytest lets a local fixture
    shadow one defined here) - these shared ones exist so *new* tests
    don't have to duplicate the same boilerplate again.
"""

import os

import pytest
from flask import Flask

import aquaPi
from aquaPi import auth
from aquaPi.driver import create_io_registry, driver_config


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')

# the 'questdb' marker itself is registered in pytest.ini


def pytest_configure(config):
    """ force the one real driver-discovery pass here, at the very start
        of the session (one per xdist worker process), before any
        fixture or test runs - guarantees DriverShelly's real mDNS
        network scan (_ShellyBase.find_ports(), shared by all 3 Shelly
        driver classes - genuine network I/O, 2 passes x 1.5s,
        regardless of simulation mode, since there's no local/hardware
        distinction for a network device) is skipped. No test needs it:
        test_driver_shelly.py tests DriverShellyInput.read()/_identify()
        directly, mocking requests.get, never touching find_ports()/
        create_io_registry() at all.

        Must happen here, not inside a fixture: MachineRoom.__init__
        unconditionally resets driver_config['DRIVER_BLACKLIST'] from
        its own (test) globals (empty, for every test fixture) before
        its own create_io_registry() call - setting the blacklist
        anywhere but before the very first call in the whole session
        risks losing that race against whichever test's MachineRoom
        happens to construct first. create_io_registry() is idempotent
        (a later call, from any test's own session fixture or from
        MachineRoom.__init__ itself, is then just a no-op regardless of
        what the blacklist becomes afterward), so doing the real pass
        right here, with the blacklist already correct, is sufficient
        for the whole session. Found while investigating overall pytest
        runtime.
    """
    driver_config['DRIVER_BLACKLIST'] = [
        'DriverShellyRelay', 'DriverShellyDimmer', 'DriverShellyInput',
    ]
    create_io_registry()


@pytest.fixture(autouse=True, scope='session')
def io_registry():
    """ the node drivers (even in simulation) need the IoRegistry singleton;
        autouse so every test gets it without asking for it explicitly
    """
    create_io_registry()


@pytest.fixture(autouse=True)
def _isolate_timedb_store():
    """ TimeDbMemory._store is a class-level dict keyed by node NAME and
        never cleared - two tests that use the same History name would
        otherwise share (and poison) each other's deque, e.g. one test's
        tiny capacity leaves a deque(maxlen=0) that setdefault() then hands
        to the next test. Wipe it around every test so distribution/order
        (xdist) can't make the suite flaky.
    """
    from aquaPi.machineroom.hist_nodes import TimeDbMemory
    TimeDbMemory._store.clear()
    yield
    TimeDbMemory._store.clear()


@pytest.fixture
def users_db_path(tmp_path):
    """ a fresh, temporary users.sqlite path for the current test only """
    return str(tmp_path / 'users.sqlite')


@pytest.fixture
def wiring_db_path(tmp_path):
    """ a fresh, temporary wiring.sqlite path for the current test only """
    return str(tmp_path / 'wiring.sqlite')


@pytest.fixture
def minimal_app(tmp_path):
    """ a minimal Flask app in testing mode: only the 'auth' blueprint
        plus a stand-in for the SPA's '/' route that 'login'/'logout'
        redirect to - no MachineRoom/MsgBus/hardware involved.
        Register additional blueprints (e.g. 'api.bp') in the test itself
        via 'minimal_app.register_blueprint(...)' if needed.
    """
    app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
    app.config['INSTANCE_PATH'] = str(tmp_path)
    app.config['TESTING'] = True
    app.config['APP_NAME'] = 'aquaPi'
    app.config['APP_VERSION'] = 'test'

    auth.init_app(app)
    app.register_blueprint(auth.bp)

    @app.route('/', endpoint='spa.spa')
    def spa_stub():
        return 'spa'

    return app


@pytest.fixture
def minimal_client(minimal_app):
    return minimal_app.test_client()

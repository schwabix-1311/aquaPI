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
from aquaPi.driver import create_io_registry


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')

# the 'questdb' marker itself is registered in pytest.ini


@pytest.fixture(autouse=True, scope='session')
def io_registry():
    """ the node drivers (even in simulation) need the IoRegistry singleton;
        autouse so every test gets it without asking for it explicitly
    """
    create_io_registry()


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

    auth.init_app(app)
    app.register_blueprint(auth.bp)

    @app.route('/', endpoint='spa.spa')
    def spa_stub():
        return 'spa'

    return app


@pytest.fixture
def minimal_client(minimal_app):
    return minimal_app.test_client()

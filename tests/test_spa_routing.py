#!/usr/bin/env python3
""" Tests for aquaPi/pages/spa.py's catch-all route (history-mode routing).

    Every other test file registers a stand-in `@app.route('/',
    endpoint='spa.spa')` stub (they only need `url_for('spa.spa')` to
    resolve for login/logout redirects) - this file is the only one that
    registers the real `pages.spa.bp` blueprint, to exercise its actual
    catch-all behavior.
"""

import os

import pytest
from flask import Flask

import aquaPi
from aquaPi.pages import spa


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')


@pytest.fixture
def app():
    app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
    app.config['TESTING'] = True
    app.config['APP_NAME'] = 'aquaPi'
    app.register_blueprint(spa.bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_root_serves_the_spa_shell(client):
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'id="app"' in resp.data


def test_client_side_route_path_serves_the_spa_shell_too(client):
    # a direct load or refresh of a vue-router history-mode path (no
    # matching Flask route) must fall through to the same SPA shell
    resp = client.get('/wiring')
    assert resp.status_code == 200
    assert b'id="app"' in resp.data


def test_unmatched_api_path_is_not_swallowed_by_the_catchall(client):
    # the catch-all must not turn a genuine API 404 into a 200 SPA shell
    resp = client.get('/api/does-not-exist')
    assert resp.status_code == 404

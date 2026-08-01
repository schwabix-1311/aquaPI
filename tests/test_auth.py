#!/usr/bin/env python3
""" Integration tests for aquaPi/auth.py (Flask-Login wiring, roles_required)

    These tests build a minimal Flask app (registering only the auth
    blueprint, plus a couple of dummy protected routes) instead of the
    full aquaPi app, so they don't need a running MachineRoom/MsgBus
    (no hardware/simulation drivers involved).
"""

import os
from http import HTTPStatus

import pytest
from flask import Flask
from flask_login import login_required

import aquaPi
from aquaPi import auth, db


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')


@pytest.fixture
def app(tmp_path):
    app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
    app.config['INSTANCE_PATH'] = str(tmp_path)
    app.config['TESTING'] = True

    auth.init_app(app)
    app.register_blueprint(auth.bp)

    # login()/logout() redirect to 'spa.spa' on success - provide a stand-in
    @app.route('/', endpoint='spa.spa')
    def spa_stub():
        return 'spa'

    @app.route('/api/protected')
    @login_required
    def protected():
        return 'ok'

    @app.route('/protected-page')
    @login_required
    def protected_page():
        return 'ok'

    @app.route('/api/operator-only')
    @auth.roles_required('operator', 'admin')
    def operator_only():
        return 'ok'

    @app.route('/api/admin-only')
    @auth.roles_required('admin')
    def admin_only():
        return 'ok'

    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def default_admin_password(app):
    """ init_app() (called in the 'app' fixture) already created the
        default admin - fetch its generated password from the DB path
        isn't possible (only the hash is stored), so instead we create
        our own known users directly for deterministic tests.
    """
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    db.create_user(users_db, 'viewer1', 'viewerPass1', role='viewer')
    db.create_user(users_db, 'operator1', 'operatorPass1', role='operator')
    db.create_user(users_db, 'admin1', 'adminPass1', role='admin')


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


def test_default_admin_created_on_first_start(app):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    users = db.list_users(users_db)
    assert any(u['username'] == 'admin' and u['role'] == 'admin' for u in users)


def test_unauthenticated_api_access_returns_401(client):
    resp = client.get('/api/protected')
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


def test_unauthenticated_page_access_redirects_to_login(client):
    resp = client.get('/protected-page')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_login_wrong_password_fails(client, default_admin_password):
    resp = _login(client, 'viewer1', 'wrong-password')
    assert resp.status_code == HTTPStatus.OK  # re-renders login form
    assert client.get('/api/protected').status_code == HTTPStatus.UNAUTHORIZED


def test_login_success_grants_access(client, default_admin_password):
    resp = _login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == 302
    assert client.get('/api/protected').status_code == HTTPStatus.OK


def test_logout_revokes_access(client, default_admin_password):
    _login(client, 'viewer1', 'viewerPass1')
    assert client.get('/api/protected').status_code == HTTPStatus.OK

    client.get('/logout')
    assert client.get('/api/protected').status_code == HTTPStatus.UNAUTHORIZED


def test_viewer_cannot_access_operator_route(client, default_admin_password):
    _login(client, 'viewer1', 'viewerPass1')
    assert client.get('/api/operator-only').status_code == HTTPStatus.FORBIDDEN


def test_operator_can_access_operator_route(client, default_admin_password):
    _login(client, 'operator1', 'operatorPass1')
    assert client.get('/api/operator-only').status_code == HTTPStatus.OK


def test_operator_cannot_access_admin_route(client, default_admin_password):
    _login(client, 'operator1', 'operatorPass1')
    assert client.get('/api/admin-only').status_code == HTTPStatus.FORBIDDEN


def test_admin_can_access_admin_and_operator_routes(client, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    assert client.get('/api/admin-only').status_code == HTTPStatus.OK
    assert client.get('/api/operator-only').status_code == HTTPStatus.OK


def test_admin_can_list_and_create_users(client, default_admin_password):
    _login(client, 'admin1', 'adminPass1')

    resp = client.get('/api/users/')
    assert resp.status_code == HTTPStatus.OK
    usernames = {u['username'] for u in resp.get_json()}
    assert {'admin', 'viewer1', 'operator1', 'admin1'} <= usernames

    resp = client.post('/api/users/', json={
        'username': 'newop', 'password': 'newopPass1', 'role': 'operator'
    })
    assert resp.status_code == HTTPStatus.CREATED
    assert resp.get_json()['role'] == 'operator'


def test_viewer_cannot_create_users(client, default_admin_password):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.post('/api/users/', json={
        'username': 'sneaky', 'password': 'x', 'role': 'admin'
    })
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_create_user_invalid_role_rejected(client, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    resp = client.post('/api/users/', json={
        'username': 'weird', 'password': 'x', 'role': 'superuser'
    })
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_secret_key_persists_across_app_instances(tmp_path):
    app1 = Flask(__name__)
    app1.config['INSTANCE_PATH'] = str(tmp_path)
    auth.init_app(app1)

    app2 = Flask(__name__)
    app2.config['INSTANCE_PATH'] = str(tmp_path)
    auth.init_app(app2)

    assert app1.config['SECRET_KEY'] == app2.config['SECRET_KEY']

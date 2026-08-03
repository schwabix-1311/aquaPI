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


def _xhr_login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       headers={'X-Requested-With': 'XMLHttpRequest'})


def test_xhr_login_success_returns_json(client, default_admin_password):
    resp = _xhr_login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == {'result': 'SUCCESS'}
    assert client.get('/api/protected').status_code == HTTPStatus.OK


def test_xhr_login_wrong_password_returns_json_error(client, default_admin_password):
    resp = _xhr_login(client, 'viewer1', 'wrong-password')
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
    body = resp.get_json()
    assert body['result'] == 'ERROR'
    assert 'message' in body
    assert client.get('/api/protected').status_code == HTTPStatus.UNAUTHORIZED


def test_xhr_login_while_locked_out_returns_json_error(client, default_admin_password, monkeypatch):
    monkeypatch.setattr(db, 'LOGIN_MAX_ATTEMPTS', 1)
    _xhr_login(client, 'viewer1', 'wrong-password')  # trips the lockout

    resp = _xhr_login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == HTTPStatus.TOO_MANY_REQUESTS
    body = resp.get_json()
    assert body['result'] == 'ERROR'


def test_plain_form_login_unaffected_by_json_support(client, default_admin_password):
    # a normal (non-XHR) browser login must keep getting the existing
    # redirect/re-render behavior, unchanged
    resp = _login(client, 'viewer1', 'wrong-password')
    assert resp.status_code == HTTPStatus.OK  # re-renders login form
    assert resp.content_type.startswith('text/html')

    resp = _login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == 302


def test_xhr_logout_returns_json(client, default_admin_password):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/logout', headers={'X-Requested-With': 'XMLHttpRequest'})
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == {'result': 'SUCCESS'}
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


def test_current_user_endpoint_returns_own_info(client, default_admin_password):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.get('/api/users/me')
    assert resp.status_code == HTTPStatus.OK
    body = resp.get_json()
    assert body['username'] == 'operator1'
    assert body['role'] == 'operator'
    assert 'password_hash' not in body


def test_current_user_endpoint_requires_login(client):
    resp = client.get('/api/users/me')
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


def test_admin_can_update_user_role(client, app, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']

    resp = client.put(f'/api/users/{user_id}', json={'role': 'operator'})
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json()['role'] == 'operator'

    row = db.get_user_by_id(users_db, user_id)
    assert row['role'] == 'operator'


def test_admin_can_reset_user_password(client, app, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']

    resp = client.put(f'/api/users/{user_id}', json={'password': 'brandNewPass1'})
    assert resp.status_code == HTTPStatus.OK

    client.get('/logout')
    resp = _login(client, 'viewer1', 'brandNewPass1')
    assert resp.status_code == 302


def test_update_user_invalid_role_rejected(client, app, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']

    resp = client.put(f'/api/users/{user_id}', json={'role': 'superuser'})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_update_unknown_user_returns_404(client, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    resp = client.put('/api/users/999999', json={'role': 'operator'})
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_cannot_demote_last_remaining_admin(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    # remove the two extra admins ('admin', 'admin1') so exactly one remains
    admin_default_id = db.get_user_by_username(users_db, 'admin')['id']
    db.delete_user(users_db, admin_default_id)

    _login(client, 'admin1', 'adminPass1')
    admin1_id = db.get_user_by_username(users_db, 'admin1')['id']

    resp = client.put(f'/api/users/{admin1_id}', json={'role': 'viewer'})
    assert resp.status_code == HTTPStatus.BAD_REQUEST

    row = db.get_user_by_id(users_db, admin1_id)
    assert row['role'] == 'admin'


def test_admin_can_delete_user(client, app, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']

    resp = client.delete(f'/api/users/{user_id}')
    assert resp.status_code == HTTPStatus.NO_CONTENT
    assert db.get_user_by_id(users_db, user_id) is None


def test_cannot_delete_last_remaining_admin(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    admin_default_id = db.get_user_by_username(users_db, 'admin')['id']
    db.delete_user(users_db, admin_default_id)

    _login(client, 'admin1', 'adminPass1')
    admin1_id = db.get_user_by_username(users_db, 'admin1')['id']

    resp = client.delete(f'/api/users/{admin1_id}')
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert db.get_user_by_id(users_db, admin1_id) is not None


def test_viewer_cannot_update_or_delete_users(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    operator_id = db.get_user_by_username(users_db, 'operator1')['id']

    _login(client, 'viewer1', 'viewerPass1')
    assert client.put(f'/api/users/{operator_id}', json={'role': 'admin'}).status_code == HTTPStatus.FORBIDDEN
    assert client.delete(f'/api/users/{operator_id}').status_code == HTTPStatus.FORBIDDEN


def test_secret_key_persists_across_app_instances(tmp_path):
    app1 = Flask(__name__)
    app1.config['INSTANCE_PATH'] = str(tmp_path)
    auth.init_app(app1)

    app2 = Flask(__name__)
    app2.config['INSTANCE_PATH'] = str(tmp_path)
    auth.init_app(app2)

    assert app1.config['SECRET_KEY'] == app2.config['SECRET_KEY']


# --- login lockout (Step 22) -----------------------------------------------

def test_login_locks_out_after_too_many_failed_attempts(client, app, default_admin_password, monkeypatch):
    monkeypatch.setattr(db, 'LOGIN_MAX_ATTEMPTS', 3)

    for _ in range(3):
        resp = _login(client, 'viewer1', 'wrong-password')
        assert resp.status_code == HTTPStatus.OK

    # 3rd failure triggered the lockout - even the correct password is now rejected
    resp = _login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == HTTPStatus.OK  # re-renders login form, no redirect
    assert client.get('/api/protected').status_code == HTTPStatus.UNAUTHORIZED


def test_login_lockout_is_per_username(client, default_admin_password, monkeypatch):
    monkeypatch.setattr(db, 'LOGIN_MAX_ATTEMPTS', 2)

    for _ in range(2):
        _login(client, 'viewer1', 'wrong-password')

    # viewer1 is now locked out, but operator1 must be unaffected
    resp = _login(client, 'operator1', 'operatorPass1')
    assert resp.status_code == 302


def test_successful_login_clears_previous_failed_attempts(client, app, default_admin_password, monkeypatch):
    monkeypatch.setattr(db, 'LOGIN_MAX_ATTEMPTS', 3)

    _login(client, 'viewer1', 'wrong-password')
    _login(client, 'viewer1', 'wrong-password')
    resp = _login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == 302  # successful login, attempts were not yet exhausted

    client.get('/logout')
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    key = 'viewer1'
    assert db.is_login_locked_out(users_db, key) == (False, 0)


# --- self-service password reset (Step 22) ---------------------------------

def test_request_password_reset_page_loads(client):
    resp = client.get('/reset-password')
    assert resp.status_code == HTTPStatus.OK


def test_request_password_reset_shows_generic_confirmation_for_unknown_user(client):
    resp = client.post('/reset-password', data={'username': 'nobody-here'})
    assert resp.status_code == HTTPStatus.OK
    assert b'password reset link has been sent' in resp.data.lower() \
        or b'reset link has been sent'.lower() in resp.data.lower()


def test_request_password_reset_creates_token_for_user_with_email(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']
    db.set_user_email(users_db, user_id, 'viewer1@example.com')

    resp = client.post('/reset-password', data={'username': 'viewer1'})
    assert resp.status_code == HTTPStatus.OK
    # no Email channel configured in this test app -> sending fails, but the
    # generic confirmation is shown either way, and no token/exception leaks
    assert b'password reset' in resp.data.lower()


def test_confirm_password_reset_with_valid_token_sets_new_password(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']
    token = db.create_password_reset_token(users_db, user_id)

    resp = client.post(f'/reset-password/{token}',
                       data={'password': 'brandNewPass1', 'password2': 'brandNewPass1'})
    assert resp.status_code == 302

    resp = _login(client, 'viewer1', 'brandNewPass1')
    assert resp.status_code == 302


def test_confirm_password_reset_mismatched_passwords_rejected(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']
    token = db.create_password_reset_token(users_db, user_id)

    resp = client.post(f'/reset-password/{token}',
                       data={'password': 'brandNewPass1', 'password2': 'somethingElse'})
    assert resp.status_code == HTTPStatus.OK  # re-renders the form

    # original password must still work
    resp = _login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == 302


def test_confirm_password_reset_invalid_token_shows_invalid_state(client):
    resp = client.get('/reset-password/not-a-real-token')
    assert resp.status_code == HTTPStatus.OK
    assert b'invalid' in resp.data.lower() or b'expired' in resp.data.lower()


def test_confirm_password_reset_token_is_single_use(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']
    token = db.create_password_reset_token(users_db, user_id)

    client.post(f'/reset-password/{token}',
               data={'password': 'brandNewPass1', 'password2': 'brandNewPass1'})

    resp = client.post(f'/reset-password/{token}',
                       data={'password': 'anotherPass2', 'password2': 'anotherPass2'})
    assert resp.status_code == HTTPStatus.OK
    assert b'invalid' in resp.data.lower() or b'expired' in resp.data.lower()


# --- email field on user CRUD API (Step 22) ---------------------------------

def test_admin_can_create_user_with_email(client, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    resp = client.post('/api/users/', json={
        'username': 'withemail', 'password': 'pwd12345', 'role': 'viewer',
        'email': 'withemail@example.com',
    })
    assert resp.status_code == HTTPStatus.CREATED
    assert resp.get_json()['email'] == 'withemail@example.com'


def test_admin_can_update_user_email(client, app, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']

    resp = client.put(f'/api/users/{user_id}', json={'email': 'viewer1@example.com'})
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json()['email'] == 'viewer1@example.com'


def test_current_user_endpoint_includes_email(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'operator1')['id']
    db.set_user_email(users_db, user_id, 'operator1@example.com')

    _login(client, 'operator1', 'operatorPass1')
    resp = client.get('/api/users/me')
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json()['email'] == 'operator1@example.com'

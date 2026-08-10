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
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
    assert client.get('/api/protected').status_code == HTTPStatus.UNAUTHORIZED


def test_login_success_grants_access(client, default_admin_password):
    resp = _login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == {'result': 'SUCCESS'}
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
    assert resp.status_code == HTTPStatus.OK


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


def test_suggest_password_returns_varying_passwords(client, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    passwords = {client.get('/api/users/suggest-password').get_json()['password']
                 for _ in range(5)}
    assert all(passwords)
    assert len(passwords) > 1


def test_viewer_cannot_suggest_password(client, default_admin_password):
    _login(client, 'viewer1', 'viewerPass1')
    resp = client.get('/api/users/suggest-password')
    assert resp.status_code == HTTPStatus.FORBIDDEN


# --- account password delivery on create/update ----------------------------

class _FakeSMTP:
    sent = []

    def __init__(self, server):
        self.server = server

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, login, pwd):
        pass

    def send_message(self, msg):
        _FakeSMTP.sent.append(msg)


class _RaisingSMTP:
    def __init__(self, server):
        raise OSError('smtp unreachable')


def _configure_email_channel(users_db):
    db.set_notification_config(users_db, 'Email', [{
        'from': 'aquapi@example.com', 'server': 'smtp.example.com',
        'login': 'aquapi', 'pwd': 'secret',
    }])


def test_create_user_without_email_delivers_via_log(client, app, default_admin_password, caplog):
    _login(client, 'admin1', 'adminPass1')
    with caplog.at_level('WARNING', logger='aquaPi.auth'):
        resp = client.post('/api/users/', json={
            'username': 'newop', 'password': 'newopPass1', 'role': 'operator'
        })
    assert resp.status_code == HTTPStatus.CREATED
    assert resp.get_json()['password_delivery'] == 'log'
    assert any('newop' in rec.message and 'newopPass1' in rec.message for rec in caplog.records)


def test_create_user_with_email_and_working_smtp_delivers_via_email(
        client, app, default_admin_password, monkeypatch):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    _configure_email_channel(users_db)
    _FakeSMTP.sent = []
    monkeypatch.setattr(db.smtplib, 'SMTP', _FakeSMTP)

    _login(client, 'admin1', 'adminPass1')
    resp = client.post('/api/users/', json={
        'username': 'newop2', 'password': 'newopPass2', 'role': 'operator',
        'email': 'newop2@example.com',
    })
    assert resp.status_code == HTTPStatus.CREATED
    assert resp.get_json()['password_delivery'] == 'email'
    assert 'password' not in resp.get_json()
    assert len(_FakeSMTP.sent) == 1


def test_create_user_with_email_but_broken_smtp_falls_back_to_log(
        client, app, default_admin_password, monkeypatch, caplog):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    _configure_email_channel(users_db)
    monkeypatch.setattr(db.smtplib, 'SMTP', _RaisingSMTP)

    _login(client, 'admin1', 'adminPass1')
    with caplog.at_level('WARNING', logger='aquaPi.auth'):
        resp = client.post('/api/users/', json={
            'username': 'newop3', 'password': 'newopPass3', 'role': 'operator',
            'email': 'newop3@example.com',
        })
    assert resp.status_code == HTTPStatus.CREATED
    assert resp.get_json()['password_delivery'] == 'log'
    assert any('newop3' in rec.message and 'newopPass3' in rec.message for rec in caplog.records)


def test_update_user_password_delivers_and_reports_delivery(
        client, app, default_admin_password, monkeypatch):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    _configure_email_channel(users_db)
    _FakeSMTP.sent = []
    monkeypatch.setattr(db.smtplib, 'SMTP', _FakeSMTP)
    db.set_user_email(users_db, db.get_user_by_username(users_db, 'viewer1')['id'],
                      'viewer1@example.com')
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']

    _login(client, 'admin1', 'adminPass1')
    resp = client.put(f'/api/users/{user_id}', json={'password': 'brandNewPass2'})
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json()['password_delivery'] == 'email'


def test_update_user_role_only_reports_no_password_delivery(
        client, app, default_admin_password):
    _login(client, 'admin1', 'adminPass1')
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']

    resp = client.put(f'/api/users/{user_id}', json={'role': 'operator'})
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json()['password_delivery'] is None


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
        assert resp.status_code == HTTPStatus.UNAUTHORIZED

    # 3rd failure triggered the lockout - even the correct password is now rejected
    resp = _login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert client.get('/api/protected').status_code == HTTPStatus.UNAUTHORIZED


def test_login_lockout_is_per_username(client, default_admin_password, monkeypatch):
    monkeypatch.setattr(db, 'LOGIN_MAX_ATTEMPTS', 2)

    for _ in range(2):
        _login(client, 'viewer1', 'wrong-password')

    # viewer1 is now locked out, but operator1 must be unaffected
    resp = _login(client, 'operator1', 'operatorPass1')
    assert resp.status_code == HTTPStatus.OK


def test_successful_login_clears_previous_failed_attempts(client, app, default_admin_password, monkeypatch):
    monkeypatch.setattr(db, 'LOGIN_MAX_ATTEMPTS', 3)

    _login(client, 'viewer1', 'wrong-password')
    _login(client, 'viewer1', 'wrong-password')
    resp = _login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == HTTPStatus.OK  # successful login, attempts were not yet exhausted

    client.get('/logout')
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    key = 'viewer1'
    assert db.is_login_locked_out(users_db, key) == (False, 0)


# --- self-service password reset (Step 22) ---------------------------------

def test_request_password_reset_page_loads(client):
    # no standalone page anymore - a plain GET just bounces to the SPA
    resp = client.get('/reset-password')
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/'


def test_request_password_reset_bridges_emailed_link_into_the_spa(client):
    # a real (non-XHR) browser navigation from the emailed link must not
    # be validated/consumed server-side - just redirected into the SPA's
    # hash-routed 'reset-password' route, which re-validates client-side
    resp = client.get('/reset-password/some-token')
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/#/reset-password/some-token'


def test_request_password_reset_shows_generic_confirmation_for_unknown_user(client):
    resp = client.post('/reset-password', data={'username': 'nobody-here'},
                       headers={'X-Requested-With': 'XMLHttpRequest'})
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == {'result': 'SUCCESS'}


def test_request_password_reset_creates_token_for_user_with_email(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']
    db.set_user_email(users_db, user_id, 'viewer1@example.com')

    resp = client.post('/reset-password', data={'username': 'viewer1'},
                       headers={'X-Requested-With': 'XMLHttpRequest'})
    assert resp.status_code == HTTPStatus.OK
    # no Email channel configured in this test app -> sending fails, but the
    # generic confirmation is returned either way, and no token/exception leaks
    assert resp.get_json() == {'result': 'SUCCESS'}


def test_confirm_password_reset_with_valid_token_sets_new_password(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']
    token = db.create_password_reset_token(users_db, user_id)

    resp = client.get(f'/reset-password/{token}', headers={'X-Requested-With': 'XMLHttpRequest'})
    assert resp.get_json() == {'valid': True}

    resp = client.post(f'/reset-password/{token}',
                       data={'password': 'brandNewPass1', 'password2': 'brandNewPass1'},
                       headers={'X-Requested-With': 'XMLHttpRequest'})
    assert resp.status_code == HTTPStatus.OK
    assert resp.get_json() == {'result': 'SUCCESS'}

    resp = _login(client, 'viewer1', 'brandNewPass1')
    assert resp.status_code == HTTPStatus.OK


def test_confirm_password_reset_mismatched_passwords_rejected(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']
    token = db.create_password_reset_token(users_db, user_id)

    resp = client.post(f'/reset-password/{token}',
                       data={'password': 'brandNewPass1', 'password2': 'somethingElse'},
                       headers={'X-Requested-With': 'XMLHttpRequest'})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.get_json()['result'] == 'ERROR'

    # original password must still work
    resp = _login(client, 'viewer1', 'viewerPass1')
    assert resp.status_code == HTTPStatus.OK


def test_confirm_password_reset_invalid_token_shows_invalid_state(client):
    resp = client.get('/reset-password/not-a-real-token',
                      headers={'X-Requested-With': 'XMLHttpRequest'})
    assert resp.get_json() == {'valid': False}


def test_confirm_password_reset_token_is_single_use(client, app, default_admin_password):
    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    user_id = db.get_user_by_username(users_db, 'viewer1')['id']
    token = db.create_password_reset_token(users_db, user_id)

    client.post(f'/reset-password/{token}',
                data={'password': 'brandNewPass1', 'password2': 'brandNewPass1'},
                headers={'X-Requested-With': 'XMLHttpRequest'})

    resp = client.post(f'/reset-password/{token}',
                       data={'password': 'anotherPass2', 'password2': 'anotherPass2'},
                       headers={'X-Requested-With': 'XMLHttpRequest'})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.get_json()['result'] == 'ERROR'


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

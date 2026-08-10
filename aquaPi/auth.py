#!/usr/bin/env python3
""" Authentication for aquaPi, based on Flask-Login.

    Users (username, hashed password, role) are stored in a small
    SQLite database (see aquaPi/db.py: users table), separate from
    the node topology database. Passwords are never stored in
    cleartext, only as a werkzeug password hash.

    A first, default 'admin' account (with a freshly generated random
    password) is created automatically on the very first start, see
    init_app()/db.ensure_default_admin().
"""

import logging
from functools import wraps
from os import path

from http import HTTPStatus

from flask import (Blueprint, abort, current_app, flash, jsonify,
                   redirect, render_template, request, url_for)
from flask_login import (LoginManager, UserMixin, current_user,
                         login_required, login_user, logout_user)
from werkzeug.security import check_password_hash

from . import db
from .passphrase import generate_aquatic_passphrase


log = logging.getLogger('aquaPi.auth')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


bp = Blueprint('auth', __name__)

login_manager = LoginManager()
login_manager.login_view = 'auth.login'


class User(UserMixin):
    """ thin Flask-Login wrapper around a 'users' table row
    """

    def __init__(self, user_id: int, username: str, role: str):
        self.id = user_id
        self.username = username
        self.role = role

    @staticmethod
    def from_row(row: dict) -> 'User':
        return User(row['id'], row['username'], row['role'])


def _users_db_path() -> str:
    return db.get_users_db_path(current_app.config['INSTANCE_PATH'])


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    row = db.get_user_by_id(_users_db_path(), int(user_id))
    return User.from_row(row) if row else None


@login_manager.unauthorized_handler
def unauthorized():
    # API routes must return a plain 401, not a redirect to the login page
    if request.path.startswith('/api/'):
        return jsonify(error='Unauthorized'), HTTPStatus.UNAUTHORIZED
    return redirect(url_for('auth.login', next=request.path))


def roles_required(*roles: str):
    """ require the current user to be logged in AND to have one of
        the given roles, e.g. @roles_required('operator', 'admin').
        Responds with 403 Forbidden (never 401) if the role does not
        suffice - the user IS authenticated, they just lack permission.
    """
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                log.info('User %r (role %r) denied access to %s (requires %s)',
                         current_user.username, current_user.role,
                         request.path, roles)
                if request.path.startswith('/api/'):
                    return jsonify(error='Forbidden'), HTTPStatus.FORBIDDEN
                abort(HTTPStatus.FORBIDDEN)
            return func(*args, **kwargs)
        # exposed so /api/'s self-documentation (api_index()) can append
        # the required role(s) to a route's description without every
        # docstring having to spell it out (and risk going stale)
        wrapped.required_roles = roles
        return wrapped
    return decorator


def init_app(app) -> None:
    """ wire up Flask-Login and ensure the users DB/default admin exist.
        Called once from create_app().
    """
    login_manager.init_app(app)

    users_db = db.get_users_db_path(app.config['INSTANCE_PATH'])
    created = db.ensure_default_admin(users_db)
    if created:
        username, password = created
        log.brief('=== No users found, created default admin account:')
        log.brief('===   username: %s', username)
        log.brief('===   password: %s', password)
        log.brief('=== Please log in and change this password as soon as possible!')

    # a stable SECRET_KEY is required, otherwise all sessions
    # (and thus all logins) would be invalidated on every restart
    app.config['SECRET_KEY'] = _get_or_create_secret_key(app.config['INSTANCE_PATH'])


def _get_or_create_secret_key(instance_path: str) -> str:
    """ persist a random SECRET_KEY in the instance folder, so Flask
        sessions survive an application restart
    """
    import secrets

    key_file = path.join(instance_path, 'secret_key')
    if path.exists(key_file):
        with open(key_file, 'r', encoding='ascii') as f_in:
            return f_in.read().strip()

    key = secrets.token_hex(32)
    with open(key_file, 'w', encoding='ascii') as f_out:
        f_out.write(key)
    return key


def _wants_json() -> bool:
    """ the SPA marks its own fetch()-based login/logout requests with
        this header, matching the convention already used by every
        other API call in store/modules/*.js - a normal browser form
        submit/navigation never sets it, so it keeps getting the
        existing render_template()/redirect() behavior unchanged.
    """
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if _wants_json():
            return jsonify(result='SUCCESS')
        return redirect(url_for('spa.spa'))

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        # lock out by username if known, else fall back to the remote
        # IP - this also throttles brute-forcing of unknown usernames
        lockout_key = username.strip().lower() or (request.remote_addr or 'unknown')

        locked, retry_seconds = db.is_login_locked_out(_users_db_path(), lockout_key)
        if locked:
            log.info('Login blocked for %r: locked out for %d more second(s)',
                     username, retry_seconds)
            message = (f'Too many failed login attempts. Please try again in '
                       f'{retry_seconds // 60 + 1} minute(s).')
            if _wants_json():
                return jsonify(result='ERROR', message=message), HTTPStatus.TOO_MANY_REQUESTS
            flash(message)
            return render_template('pages/login.html.jinja2')

        row = db.get_user_by_username(_users_db_path(), username)
        if row and check_password_hash(row['password_hash'], password):
            db.clear_login_attempts(_users_db_path(), lockout_key)
            login_user(User.from_row(row))
            log.info('User %r logged in', username)
            if _wants_json():
                return jsonify(result='SUCCESS')
            next_url = request.args.get('next') or url_for('spa.spa')
            return redirect(next_url)

        db.register_failed_login(_users_db_path(), lockout_key,
                                 max_attempts=db.LOGIN_MAX_ATTEMPTS,
                                 window_minutes=db.LOGIN_ATTEMPT_WINDOW_MINUTES,
                                 lockout_minutes=db.LOGIN_LOCKOUT_MINUTES)
        log.info('Failed login attempt for %r', username)
        if _wants_json():
            return jsonify(result='ERROR', message='Invalid username or password'), HTTPStatus.UNAUTHORIZED
        flash('Invalid username or password')

    return render_template('pages/login.html.jinja2')


@bp.route('/reset-password', methods=['GET', 'POST'])
def request_password_reset():
    """ self-service password reset, step 1: user enters their
        username, and - if the account has an email address on file -
        gets sent a single-use reset link. Always shows the same
        generic confirmation, regardless of whether the username
        exists or has an email, to avoid leaking account existence.
    """
    sent = False
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        row = db.get_user_by_username(_users_db_path(), username)
        if row and row.get('email'):
            token = db.create_password_reset_token(_users_db_path(), row['id'])
            reset_url = url_for('auth.confirm_password_reset', token=token, _external=True)
            db.send_password_reset_email(_users_db_path(), row['email'], reset_url)
            log.info('Password reset requested for user %r, email sent', row['username'])
        else:
            log.info('Password reset requested for unknown/emailless user %r', username)
        sent = True

    return render_template('pages/reset_password_request.html.jinja2', sent=sent)


@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def confirm_password_reset(token: str):
    """ self-service password reset, step 2: user follows the emailed
        link and sets a new password, if the token is still valid.
    """
    row = db.get_password_reset_token(_users_db_path(), token)
    if not row:
        return render_template('pages/reset_password_confirm.html.jinja2', invalid=True)

    if request.method == 'POST':
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        if not password or password != password2:
            flash('Passwords are empty or do not match')
            return render_template('pages/reset_password_confirm.html.jinja2', invalid=False)

        db.consume_password_reset_token(_users_db_path(), token, password)
        log.info('Password reset completed for user_id %r', row['user_id'])
        flash('Your password has been reset - please log in')
        return redirect(url_for('auth.login'))

    return render_template('pages/reset_password_confirm.html.jinja2', invalid=False)


@bp.route('/logout')
@login_required
def logout():
    log.info('User %r logged out', current_user.username)
    logout_user()
    if _wants_json():
        return jsonify(result='SUCCESS')
    return redirect(url_for('auth.login'))


def _user_to_dict(row: dict) -> dict:
    """ never expose the password hash via the API """
    return {'id': row['id'], 'username': row['username'], 'role': row['role'],
            'email': row.get('email')}


@bp.route('/api/users/me', methods=['GET'])
@login_required
def api_current_user():
    """ return the currently logged-in user's own info (id, username,
        role) - used by the SPA to reliably know its own role, since
        the client-side Vuex auth store is only a placeholder without
        a real tie to this server-side session.
    """
    row = db.get_user_by_id(_users_db_path(), current_user.id)
    return jsonify(_user_to_dict(row))


@bp.route('/api/users/', methods=['GET'])
@roles_required('admin')
def api_list_users():
    """ list all users """
    users = db.list_users(_users_db_path())
    return jsonify([_user_to_dict(u) for u in users])


@bp.route('/api/users/suggest-password', methods=['GET'])
@roles_required('admin')
def api_suggest_password():
    """ return a freshly generated passphrase suggestion, does not
        persist anything
    """
    return jsonify({'password': generate_aquatic_passphrase()})


def _deliver_user_password(email: str | None, username: str, password: str) -> str:
    """ deliver a newly set account password to its owner: by email if
        possible, else fall back to a one-time server log line (same
        pattern as the default-admin bootstrap, see init_app() below).
        Returns 'email' or 'log' to let the caller inform the admin.
    """
    if email and db.send_user_password_email(_users_db_path(), email, username, password):
        return 'email'
    log.brief('=== Set password for user %r: %s', username, password)
    return 'log'


@bp.route('/api/users/', methods=['POST'])
@roles_required('admin')
def api_create_user():
    """ create a new user with a role """
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')
    role = data.get('role', 'viewer')
    email = data.get('email') or None

    if not username or not password:
        return jsonify(error='username and password are required'), HTTPStatus.BAD_REQUEST
    if role not in db.VALID_ROLES:
        return jsonify(error=f'Invalid role: {role!r}'), HTTPStatus.BAD_REQUEST

    try:
        user_id = db.create_user(_users_db_path(), username, password, role=role, email=email)
    except ValueError as ex:
        return jsonify(error=str(ex)), HTTPStatus.BAD_REQUEST

    log.info('User %r created new user %r with role %r', current_user.username, username, role)
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'create_user', username, {'role': role})
    password_delivery = _deliver_user_password(email, username, password)
    return jsonify({'id': user_id, 'username': username, 'role': role, 'email': email,
                    'password_delivery': password_delivery}), HTTPStatus.CREATED


@bp.route('/api/users/<int:user_id>', methods=['PUT'])
@roles_required('admin')
def api_update_user(user_id: int):
    """ change a user's role and/or reset their password. Refuses to
        demote the last remaining admin, to avoid locking everyone out
        of admin functionality.
    """
    row = db.get_user_by_id(_users_db_path(), user_id)
    if not row:
        return jsonify(error='No such user'), HTTPStatus.NOT_FOUND

    data = request.get_json(silent=True) or {}
    role = data.get('role')
    password = data.get('password')
    email = data.get('email')

    if role is not None:
        if role not in db.VALID_ROLES:
            return jsonify(error=f'Invalid role: {role!r}'), HTTPStatus.BAD_REQUEST
        if row['role'] == 'admin' and role != 'admin' and db.count_admins(_users_db_path()) <= 1:
            return jsonify(error='Cannot remove the last remaining admin'), HTTPStatus.BAD_REQUEST
        db.update_user_role(_users_db_path(), user_id, role)
        log.info('User %r changed role of user %r to %r',
                 current_user.username, row['username'], role)
        db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                               'update_user_role', row['username'], {'role': role})

    password_delivery = None
    if password is not None:
        if not password:
            return jsonify(error='password must not be empty'), HTTPStatus.BAD_REQUEST
        db.set_user_password(_users_db_path(), user_id, password)
        log.info('User %r reset password of user %r', current_user.username, row['username'])
        db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                               'reset_user_password', row['username'])

    if email is not None:
        db.set_user_email(_users_db_path(), user_id, email)
        log.info('User %r set email of user %r', current_user.username, row['username'])
        db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                               'set_user_email', row['username'])

    if password is not None:
        effective_email = email if email is not None else row['email']
        password_delivery = _deliver_user_password(effective_email, row['username'], password)

    updated = db.get_user_by_id(_users_db_path(), user_id)
    result = _user_to_dict(updated)
    result['password_delivery'] = password_delivery
    return jsonify(result)


@bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@roles_required('admin')
def api_delete_user(user_id: int):
    """ remove a user. Refuses to remove the last remaining admin, to
        avoid locking everyone out.
    """
    row = db.get_user_by_id(_users_db_path(), user_id)
    if not row:
        return jsonify(error='No such user'), HTTPStatus.NOT_FOUND

    if row['role'] == 'admin' and db.count_admins(_users_db_path()) <= 1:
        return jsonify(error='Cannot remove the last remaining admin'), HTTPStatus.BAD_REQUEST

    db.delete_user(_users_db_path(), user_id)
    log.info('User %r deleted user %r', current_user.username, row['username'])
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'delete_user', row['username'])
    return '', HTTPStatus.NO_CONTENT


@bp.route('/api/notifications/prefs', methods=['GET'])
@login_required
def api_list_notification_prefs():
    """ list the current user's own preferred channel per alert node """
    prefs = db.list_user_notification_prefs(_users_db_path(), current_user.id)
    return jsonify(prefs)


@bp.route('/api/notifications/prefs/<alert_node_id>', methods=['PUT'])
@roles_required('operator', 'admin')
def api_set_notification_pref(alert_node_id: str):
    """ set the current user's preferred notification channel
        ('email'/'telegram'/'none') for one specific Alert node, plus an
        optional 2nd escalation channel that gets additionally notified
        once the alert has stayed active for 'escalation_after_minutes'
        (Step 28; 0 or 'none' disables escalation).
    """
    data = request.get_json(silent=True) or {}
    channel = data.get('channel', '')
    escalation_channel = data.get('escalation_channel', 'none')
    escalation_after_minutes = data.get('escalation_after_minutes', 0)

    if channel not in ('email', 'telegram', 'none'):
        return jsonify(error=f'Invalid channel: {channel!r}'), HTTPStatus.BAD_REQUEST
    if escalation_channel not in ('email', 'telegram', 'none'):
        return jsonify(error=f'Invalid escalation channel: {escalation_channel!r}'), HTTPStatus.BAD_REQUEST
    try:
        escalation_after_minutes = int(escalation_after_minutes)
        if escalation_after_minutes < 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify(error='escalation_after_minutes must be a non-negative integer'), HTTPStatus.BAD_REQUEST

    db.set_user_notification_pref(_users_db_path(), current_user.id, alert_node_id, channel,
                                  escalation_channel, escalation_after_minutes)
    log.info('User %r set notification channel %r (escalation %r after %d min) for alert %r',
             current_user.username, channel, escalation_channel, escalation_after_minutes, alert_node_id)
    return jsonify({'alert_node_id': alert_node_id, 'channel': channel,
                    'escalation_channel': escalation_channel,
                    'escalation_after_minutes': escalation_after_minutes})

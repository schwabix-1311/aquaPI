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


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('spa.spa'))

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        row = db.get_user_by_username(_users_db_path(), username)
        if row and check_password_hash(row['password_hash'], password):
            login_user(User.from_row(row))
            log.info('User %r logged in', username)
            next_url = request.args.get('next') or url_for('spa.spa')
            return redirect(next_url)

        log.info('Failed login attempt for %r', username)
        flash('Invalid username or password')

    return render_template('pages/login.html.jinja2')


@bp.route('/logout')
@login_required
def logout():
    log.info('User %r logged out', current_user.username)
    logout_user()
    return redirect(url_for('auth.login'))


def _user_to_dict(row: dict) -> dict:
    """ never expose the password hash via the API """
    return {'id': row['id'], 'username': row['username'], 'role': row['role']}


@bp.route('/api/users/', methods=['GET'])
@roles_required('admin')
def api_list_users():
    """ list all users (admin only) """
    users = db.list_users(_users_db_path())
    return jsonify([_user_to_dict(u) for u in users])


@bp.route('/api/users/', methods=['POST'])
@roles_required('admin')
def api_create_user():
    """ create a new user with a role (admin only) """
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')
    role = data.get('role', 'viewer')

    if not username or not password:
        return jsonify(error='username and password are required'), HTTPStatus.BAD_REQUEST
    if role not in db.VALID_ROLES:
        return jsonify(error=f'Invalid role: {role!r}'), HTTPStatus.BAD_REQUEST

    try:
        user_id = db.create_user(_users_db_path(), username, password, role=role)
    except ValueError as ex:
        return jsonify(error=str(ex)), HTTPStatus.BAD_REQUEST

    log.info('User %r created new user %r with role %r', current_user.username, username, role)
    return jsonify({'id': user_id, 'username': username, 'role': role}), HTTPStatus.CREATED

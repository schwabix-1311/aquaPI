#!/usr/bin/env python3
""" Tests for the users/authentication persistence in aquaPi/db.py
"""

import pytest
from werkzeug.security import check_password_hash

from aquaPi import db


@pytest.fixture
def users_db_path(tmp_path):
    return str(tmp_path / 'users.sqlite')


def test_create_user_and_get_by_username(users_db_path):
    user_id = db.create_user(users_db_path, 'alice', 'sup3rSecret!', role='operator')
    assert user_id > 0

    row = db.get_user_by_username(users_db_path, 'alice')
    assert row is not None
    assert row['username'] == 'alice'
    assert row['role'] == 'operator'
    # never store the password in plain text
    assert row['password_hash'] != 'sup3rSecret!'
    assert check_password_hash(row['password_hash'], 'sup3rSecret!')
    assert not check_password_hash(row['password_hash'], 'wrong-password')


def test_get_user_by_id(users_db_path):
    user_id = db.create_user(users_db_path, 'bob', 'pwd12345', role='viewer')
    row = db.get_user_by_id(users_db_path, user_id)
    assert row is not None
    assert row['username'] == 'bob'


def test_get_user_by_username_unknown_returns_none(users_db_path):
    assert db.get_user_by_username(users_db_path, 'nobody') is None


def test_create_user_duplicate_username_raises(users_db_path):
    db.create_user(users_db_path, 'carol', 'pwd12345', role='viewer')
    with pytest.raises(ValueError):
        db.create_user(users_db_path, 'carol', 'other-pwd', role='admin')


def test_create_user_invalid_role_raises(users_db_path):
    with pytest.raises(ValueError):
        db.create_user(users_db_path, 'dave', 'pwd12345', role='superuser')


def test_list_users(users_db_path):
    db.create_user(users_db_path, 'zoe', 'pwd12345', role='viewer')
    db.create_user(users_db_path, 'amy', 'pwd12345', role='admin')

    users = db.list_users(users_db_path)
    assert [u['username'] for u in users] == ['amy', 'zoe']  # ordered by username


def test_count_admins(users_db_path):
    assert db.count_admins(users_db_path) == 0
    db.create_user(users_db_path, 'admin1', 'pwd12345', role='admin')
    db.create_user(users_db_path, 'viewer1', 'pwd12345', role='viewer')
    assert db.count_admins(users_db_path) == 1
    db.create_user(users_db_path, 'admin2', 'pwd12345', role='admin')
    assert db.count_admins(users_db_path) == 2


def test_ensure_default_admin_creates_once(users_db_path):
    created = db.ensure_default_admin(users_db_path)
    assert created is not None
    username, password = created
    assert username == 'admin'
    assert len(password) > 8

    row = db.get_user_by_username(users_db_path, username)
    assert row['role'] == 'admin'
    assert check_password_hash(row['password_hash'], password)

    # calling again must not create a 2nd default admin / must not reset the password
    created_again = db.ensure_default_admin(users_db_path)
    assert created_again is None
    assert db.count_admins(users_db_path) == 1


def test_ensure_default_admin_skipped_if_users_exist(users_db_path):
    db.create_user(users_db_path, 'someone', 'pwd12345', role='viewer')
    created = db.ensure_default_admin(users_db_path)
    assert created is None
    assert db.count_admins(users_db_path) == 0


def test_update_user_role(users_db_path):
    user_id = db.create_user(users_db_path, 'erin', 'pwd12345', role='viewer')
    db.update_user_role(users_db_path, user_id, 'operator')
    row = db.get_user_by_id(users_db_path, user_id)
    assert row['role'] == 'operator'


def test_update_user_role_invalid_raises(users_db_path):
    user_id = db.create_user(users_db_path, 'frank', 'pwd12345', role='viewer')
    with pytest.raises(ValueError):
        db.update_user_role(users_db_path, user_id, 'superuser')


def test_update_user_role_unknown_user_raises(users_db_path):
    with pytest.raises(ValueError):
        db.update_user_role(users_db_path, 999999, 'admin')


def test_set_user_password(users_db_path):
    user_id = db.create_user(users_db_path, 'grace', 'oldPass1', role='viewer')
    db.set_user_password(users_db_path, user_id, 'newPass2')
    row = db.get_user_by_id(users_db_path, user_id)
    assert check_password_hash(row['password_hash'], 'newPass2')
    assert not check_password_hash(row['password_hash'], 'oldPass1')


def test_set_user_password_unknown_user_raises(users_db_path):
    with pytest.raises(ValueError):
        db.set_user_password(users_db_path, 999999, 'newPass2')


def test_delete_user(users_db_path):
    user_id = db.create_user(users_db_path, 'henry', 'pwd12345', role='viewer')
    db.delete_user(users_db_path, user_id)
    assert db.get_user_by_id(users_db_path, user_id) is None


def test_delete_user_unknown_user_raises(users_db_path):
    with pytest.raises(ValueError):
        db.delete_user(users_db_path, 999999)


def test_create_user_with_email(users_db_path):
    user_id = db.create_user(users_db_path, 'ivy', 'pwd12345', role='viewer',
                             email='ivy@example.com')
    row = db.get_user_by_id(users_db_path, user_id)
    assert row['email'] == 'ivy@example.com'


def test_create_user_without_email_defaults_to_none(users_db_path):
    user_id = db.create_user(users_db_path, 'jack', 'pwd12345', role='viewer')
    row = db.get_user_by_id(users_db_path, user_id)
    assert row['email'] is None


def test_set_user_email(users_db_path):
    user_id = db.create_user(users_db_path, 'kate', 'pwd12345', role='viewer')
    db.set_user_email(users_db_path, user_id, 'kate@example.com')
    row = db.get_user_by_id(users_db_path, user_id)
    assert row['email'] == 'kate@example.com'

    db.set_user_email(users_db_path, user_id, None)
    row = db.get_user_by_id(users_db_path, user_id)
    assert row['email'] is None


def test_set_user_email_unknown_user_raises(users_db_path):
    with pytest.raises(ValueError):
        db.set_user_email(users_db_path, 999999, 'x@example.com')


# --- password reset tokens (Step 22) --------------------------------------

def test_create_and_get_password_reset_token(users_db_path):
    user_id = db.create_user(users_db_path, 'liam', 'pwd12345', role='viewer')
    token = db.create_password_reset_token(users_db_path, user_id)
    assert len(token) > 16

    row = db.get_password_reset_token(users_db_path, token)
    assert row is not None
    assert row['user_id'] == user_id
    assert row['used'] == 0


def test_get_password_reset_token_unknown_returns_none(users_db_path):
    assert db.get_password_reset_token(users_db_path, 'not-a-real-token') is None


def test_get_password_reset_token_expired_returns_none(users_db_path):
    user_id = db.create_user(users_db_path, 'mia', 'pwd12345', role='viewer')
    token = db.create_password_reset_token(users_db_path, user_id, ttl_minutes=-1)
    assert db.get_password_reset_token(users_db_path, token) is None


def test_consume_password_reset_token_sets_new_password(users_db_path):
    user_id = db.create_user(users_db_path, 'noah', 'oldPass1', role='viewer')
    token = db.create_password_reset_token(users_db_path, user_id)

    db.consume_password_reset_token(users_db_path, token, 'brandNewPass1')

    row = db.get_user_by_id(users_db_path, user_id)
    assert check_password_hash(row['password_hash'], 'brandNewPass1')
    assert not check_password_hash(row['password_hash'], 'oldPass1')


def test_consume_password_reset_token_is_single_use(users_db_path):
    user_id = db.create_user(users_db_path, 'olivia', 'oldPass1', role='viewer')
    token = db.create_password_reset_token(users_db_path, user_id)

    db.consume_password_reset_token(users_db_path, token, 'brandNewPass1')

    with pytest.raises(ValueError):
        db.consume_password_reset_token(users_db_path, token, 'anotherPass2')


def test_consume_password_reset_token_invalid_raises(users_db_path):
    with pytest.raises(ValueError):
        db.consume_password_reset_token(users_db_path, 'not-a-real-token', 'newPass1')


# --- login lockout (Step 22) -----------------------------------------------

def test_is_login_locked_out_initially_false(users_db_path):
    locked, retry = db.is_login_locked_out(users_db_path, 'someuser')
    assert locked is False
    assert retry == 0


def test_register_failed_login_locks_out_after_threshold(users_db_path):
    for _ in range(2):
        db.register_failed_login(users_db_path, 'peter', max_attempts=3)
        locked, _ = db.is_login_locked_out(users_db_path, 'peter')
        assert locked is False

    db.register_failed_login(users_db_path, 'peter', max_attempts=3)
    locked, retry = db.is_login_locked_out(users_db_path, 'peter')
    assert locked is True
    assert retry > 0


def test_register_failed_login_resets_after_window_expires(users_db_path):
    # window_minutes=0 -> the very next failed attempt is treated as a
    # fresh window (count restarts at 1) instead of accumulating
    db.register_failed_login(users_db_path, 'quinn', max_attempts=2, window_minutes=0)
    db.register_failed_login(users_db_path, 'quinn', max_attempts=2, window_minutes=0)
    locked, _ = db.is_login_locked_out(users_db_path, 'quinn')
    assert locked is False


def test_clear_login_attempts(users_db_path):
    db.register_failed_login(users_db_path, 'ruth', max_attempts=1)
    locked, _ = db.is_login_locked_out(users_db_path, 'ruth')
    assert locked is True

    db.clear_login_attempts(users_db_path, 'ruth')
    locked, _ = db.is_login_locked_out(users_db_path, 'ruth')
    assert locked is False


# --- password reset email delivery (Step 22) -------------------------------

def test_send_password_reset_email_without_config_returns_false(users_db_path):
    assert db.send_password_reset_email(users_db_path, 'someone@example.com',
                                        'http://example.com/reset/abc') is False

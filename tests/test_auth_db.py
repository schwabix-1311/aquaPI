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

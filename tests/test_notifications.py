#!/usr/bin/env python3
""" Tests for notification config (Step 7):
    - aquaPi/db.py: notification_config table (system-wide Email/Telegram
      credentials)
"""

import pytest

from aquaPi import db


@pytest.fixture
def users_db_path(tmp_path):
    return str(tmp_path / 'users.sqlite')


# --- notification_config -------------------------------------------------


def test_set_and_get_notification_config(users_db_path):
    assert db.get_notification_config(users_db_path, 'Email') is None

    configs = [{'server': 'smtp.example.com', 'login': 'me', 'pwd': 'secret',
                'from': 'me@example.com', 'to': 'you@example.com'}]
    db.set_notification_config(users_db_path, 'Email', configs)

    assert db.get_notification_config(users_db_path, 'Email') == configs


def test_set_notification_config_invalid_channel_raises(users_db_path):
    with pytest.raises(ValueError):
        db.set_notification_config(users_db_path, 'Signal', [{}])


def test_set_notification_config_overwrites(users_db_path):
    db.set_notification_config(users_db_path, 'Telegram', [{'bot_token': 'a'}])
    db.set_notification_config(users_db_path, 'Telegram', [{'bot_token': 'b'}])
    assert db.get_notification_config(users_db_path, 'Telegram') == [{'bot_token': 'b'}]


def test_migrate_notification_config_from_json(users_db_path):
    globals_cfg = {
        'Email': {'server': 's', 'login': 'l', 'pwd': 'p', 'from': 'f', 'to': 't'},
        'Telegram': [{'bot_token': 'tok', 'chat_name': 'n', 'chat_id': 1}],
        'OTHER_KEY': 'ignored',
    }
    migrated = db.migrate_notification_config_from_json(globals_cfg, users_db_path)
    assert migrated is True

    # single dict gets wrapped into a list, list is kept as-is
    assert db.get_notification_config(users_db_path, 'Email') == [globals_cfg['Email']]
    assert db.get_notification_config(users_db_path, 'Telegram') == globals_cfg['Telegram']


def test_migrate_notification_config_is_idempotent(users_db_path):
    globals_cfg = {'Email': [{'server': 'orig'}]}
    assert db.migrate_notification_config_from_json(globals_cfg, users_db_path) is True

    # a 2nd migration attempt (e.g. on next app start) must not overwrite
    # values that might have been changed via the API meanwhile
    db.set_notification_config(users_db_path, 'Email', [{'server': 'changed'}])
    assert db.migrate_notification_config_from_json(globals_cfg, users_db_path) is False
    assert db.get_notification_config(users_db_path, 'Email') == [{'server': 'changed'}]


def test_migrate_notification_config_no_source(users_db_path):
    assert db.migrate_notification_config_from_json({}, users_db_path) is False
    assert db.get_notification_config(users_db_path, 'Email') is None

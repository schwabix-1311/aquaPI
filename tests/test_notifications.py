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



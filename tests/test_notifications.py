#!/usr/bin/env python3
""" Tests for notification config / per-user alert preferences (Step 7):
    - aquaPi/db.py: notification_config + user_notification_prefs tables
    - aquaPi/machineroom/alert_nodes.py: per-user channel dispatch
"""

import pytest

from aquaPi import db
from aquaPi.driver import IoRegistry, PortFunc, create_io_registry
from aquaPi.driver.base import IoPort, OutDriver
from aquaPi.machineroom.alert_nodes import Alert, AlertAbove
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.msg_types import MsgData
from aquaPi.machineroom.in_nodes import AnalogInput


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    """ the IoRegistry singleton must exist before IoRegistry.get() works,
        regardless of which other test modules already ran in this session
    """
    create_io_registry()


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


# --- user_notification_prefs ---------------------------------------------


def test_user_notification_pref_default_is_none(users_db_path):
    user_id = db.create_user(users_db_path, 'alice', 'pwd12345', role='viewer')
    assert db.get_user_notification_pref(users_db_path, user_id, 'warnungen') == 'none'


def test_set_and_get_user_notification_pref(users_db_path):
    user_id = db.create_user(users_db_path, 'bob', 'pwd12345', role='operator')
    db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'telegram')
    assert db.get_user_notification_pref(users_db_path, user_id, 'warnungen') == 'telegram'

    # overwrite
    db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email')
    assert db.get_user_notification_pref(users_db_path, user_id, 'warnungen') == 'email'


def test_set_user_notification_pref_invalid_channel_raises(users_db_path):
    user_id = db.create_user(users_db_path, 'carol', 'pwd12345', role='viewer')
    with pytest.raises(ValueError):
        db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'sms')


def test_list_user_notification_prefs(users_db_path):
    user_id = db.create_user(users_db_path, 'dave', 'pwd12345', role='viewer')
    db.set_user_notification_pref(users_db_path, user_id, 'ph_alarm', 'email')
    db.set_user_notification_pref(users_db_path, user_id, 'temp_alarm', 'telegram')

    prefs = db.list_user_notification_prefs(users_db_path, user_id)
    assert {p['alert_node_id']: p['channel'] for p in prefs} == {
        'ph_alarm': 'email', 'temp_alarm': 'telegram'
    }


def test_get_prefs_for_alert_excludes_none(users_db_path):
    u1 = db.create_user(users_db_path, 'ivy', 'pwd12345', role='viewer')
    u2 = db.create_user(users_db_path, 'jack', 'pwd12345', role='operator')
    u3 = db.create_user(users_db_path, 'kate', 'pwd12345', role='admin')

    db.set_user_notification_pref(users_db_path, u1, 'warnungen', 'email')
    db.set_user_notification_pref(users_db_path, u2, 'warnungen', 'telegram')
    db.set_user_notification_pref(users_db_path, u3, 'warnungen', 'none')
    # a pref for a different alert must not show up
    db.set_user_notification_pref(users_db_path, u1, 'other_alert', 'telegram')

    prefs = db.get_prefs_for_alert(users_db_path, 'warnungen')
    by_user = {p['username']: p['channel'] for p in prefs}
    assert by_user == {'ivy': 'email', 'jack': 'telegram'}
    assert 'kate' not in by_user


def test_get_prefs_for_alert_no_prefs_returns_empty(users_db_path):
    assert db.get_prefs_for_alert(users_db_path, 'unknown_alert') == []


def test_user_notification_prefs_cascade_on_user_delete(users_db_path):
    user_id = db.create_user(users_db_path, 'leo', 'pwd12345', role='viewer')
    db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email')

    conn = db.get_users_connection(users_db_path)
    try:
        with conn:
            conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    finally:
        conn.close()

    assert db.get_prefs_for_alert(users_db_path, 'warnungen') == []


# --- Alert._notify_user_prefs dispatch ------------------------------------


class _FakeTextDriver(OutDriver):
    """ minimal stand-in for a Tout driver, recording what was written """

    def __init__(self, cfg=None, func=PortFunc.Tout):
        super().__init__(cfg or {}, func)
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)


@pytest.fixture
def fake_text_ports(monkeypatch):
    """ register fake 'Email #1'/'Telegram #1' ports so Alert can send
        through them without any real network access
    """
    email_driver = _FakeTextDriver()
    telegram_driver = _FakeTextDriver()

    io_ports = {
        'Email #1': IoPort(PortFunc.Tout, lambda cfg, func: email_driver, {}, []),
        'Telegram #1': IoPort(PortFunc.Tout, lambda cfg, func: telegram_driver, {}, []),
    }
    monkeypatch.setattr(IoRegistry, '_map', io_ports)
    return {'email': email_driver, 'telegram': telegram_driver}


def test_alert_notifies_users_by_preferred_channel(users_db_path, fake_text_ports):
    u1 = db.create_user(users_db_path, 'mia', 'pwd12345', role='viewer')
    u2 = db.create_user(users_db_path, 'noah', 'pwd12345', role='operator')
    db.set_current_users_db_path(users_db_path)
    try:
        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), '', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        db.set_user_notification_pref(users_db_path, u1, alert.id, 'email')
        db.set_user_notification_pref(users_db_path, u2, alert.id, 'telegram')

        alert.listen(MsgData(sensor.id, 30.0))

        assert fake_text_ports['email'].written
        assert fake_text_ports['telegram'].written
        assert 'HOCH' in fake_text_ports['email'].written[0]
        assert 'HOCH' in fake_text_ports['telegram'].written[0]

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)


def test_alert_without_prefs_sends_nothing_via_prefs(users_db_path, fake_text_ports):
    db.set_current_users_db_path(users_db_path)
    try:
        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), '', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        # no exception, no message sent, since nobody configured a pref
        alert.listen(MsgData(sensor.id, 30.0))

        assert fake_text_ports['email'].written == []
        assert fake_text_ports['telegram'].written == []

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)


def test_alert_notify_user_prefs_noop_without_current_db_path(fake_text_ports):
    """ if MachineRoom never set a 'current' users DB path (e.g. some
        standalone unit test), per-user notification is silently skipped
    """
    db.set_current_users_db_path(None)
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), '', repeat=3600)
    alert.plugin(bus)

    alert.listen(MsgData(sensor.id, 30.0))

    assert fake_text_ports['email'].written == []
    assert fake_text_ports['telegram'].written == []

    bus.teardown()

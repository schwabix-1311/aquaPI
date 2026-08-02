#!/usr/bin/env python3
""" Tests for Step 28 (alarm escalation): user_notification_prefs gained
    'escalation_channel'/'escalation_after_minutes', and Alert notifies
    that 2nd channel once an alert has stayed continuously active for
    at least that long.
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
    create_io_registry()


@pytest.fixture
def users_db_path(tmp_path):
    return str(tmp_path / 'users.sqlite')


# --- db.py: escalation prefs ----------------------------------------------


def test_set_user_notification_pref_default_no_escalation(users_db_path):
    user_id = db.create_user(users_db_path, 'alice', 'pwd12345', role='viewer')
    db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email')

    prefs = db.list_user_notification_prefs(users_db_path, user_id)
    assert prefs == [{'alert_node_id': 'warnungen', 'channel': 'email',
                      'escalation_channel': 'none', 'escalation_after_minutes': 0}]


def test_set_user_notification_pref_with_escalation(users_db_path):
    user_id = db.create_user(users_db_path, 'bob', 'pwd12345', role='operator')
    db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email',
                                  escalation_channel='telegram', escalation_after_minutes=30)

    prefs = db.list_user_notification_prefs(users_db_path, user_id)
    assert prefs == [{'alert_node_id': 'warnungen', 'channel': 'email',
                      'escalation_channel': 'telegram', 'escalation_after_minutes': 30}]


def test_set_user_notification_pref_invalid_escalation_channel_raises(users_db_path):
    user_id = db.create_user(users_db_path, 'carol', 'pwd12345', role='viewer')
    with pytest.raises(ValueError):
        db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email',
                                      escalation_channel='sms')


def test_set_user_notification_pref_negative_escalation_minutes_raises(users_db_path):
    user_id = db.create_user(users_db_path, 'dave', 'pwd12345', role='viewer')
    with pytest.raises(ValueError):
        db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email',
                                      escalation_channel='telegram',
                                      escalation_after_minutes=-1)


def test_get_prefs_for_alert_includes_escalation_fields(users_db_path):
    user_id = db.create_user(users_db_path, 'eve', 'pwd12345', role='viewer')
    db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email',
                                  escalation_channel='telegram', escalation_after_minutes=15)

    prefs = db.get_prefs_for_alert(users_db_path, 'warnungen')
    assert len(prefs) == 1
    assert prefs[0]['escalation_channel'] == 'telegram'
    assert prefs[0]['escalation_after_minutes'] == 15


def test_migrate_adds_escalation_columns_to_existing_prefs_table(users_db_path):
    """ a DB created before Step 28 only had 'channel', not the two new
        columns - get_users_connection() must migrate it transparently
    """
    conn = db.get_users_connection(users_db_path)
    conn.execute('DROP TABLE user_notification_prefs')
    conn.execute("""
        CREATE TABLE user_notification_prefs (
            user_id       INTEGER NOT NULL,
            alert_node_id TEXT NOT NULL,
            channel       TEXT NOT NULL DEFAULT 'none',
            PRIMARY KEY (user_id, alert_node_id)
        )
    """)
    conn.close()

    # re-opening (as any db.* call does) must transparently add the columns
    user_id = db.create_user(users_db_path, 'frank', 'pwd12345', role='viewer')
    db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email',
                                  escalation_channel='telegram', escalation_after_minutes=5)
    prefs = db.list_user_notification_prefs(users_db_path, user_id)
    assert prefs[0]['escalation_after_minutes'] == 5


# --- Alert escalation dispatch --------------------------------------------


class _FakeTextDriver(OutDriver):
    """ minimal stand-in for a Tout driver, recording what was written """

    def __init__(self, cfg=None, func=PortFunc.Tout):
        super().__init__(cfg or {}, func)
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)


@pytest.fixture
def fake_text_ports(monkeypatch):
    email_driver = _FakeTextDriver()
    telegram_driver = _FakeTextDriver()

    io_ports = {
        'Email #1': IoPort(PortFunc.Tout, lambda cfg, func: email_driver, {}, []),
        'Telegram #1': IoPort(PortFunc.Tout, lambda cfg, func: telegram_driver, {}, []),
    }
    monkeypatch.setattr(IoRegistry, '_map', io_ports)
    return {'email': email_driver, 'telegram': telegram_driver}


@pytest.fixture
def fake_clock(monkeypatch):
    """ control the monotonic() clock seen by alert_nodes.py, so
        escalation timing can be tested deterministically
    """
    state = {'now': 1000.0}

    def _monotonic():
        return state['now']

    import aquaPi.machineroom.alert_nodes as alert_nodes_mod
    monkeypatch.setattr(alert_nodes_mod, 'monotonic', _monotonic)

    def advance(seconds):
        state['now'] += seconds

    return advance


def test_alert_escalates_after_configured_duration(users_db_path, fake_text_ports, fake_clock):
    user_id = db.create_user(users_db_path, 'mia', 'pwd12345', role='viewer')
    db.set_current_users_db_path(users_db_path)
    try:
        db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email',
                                      escalation_channel='telegram', escalation_after_minutes=10)

        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), '', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        # alert starts, only primary (email) channel gets notified
        alert.listen(MsgData(sensor.id, 30.0))
        assert fake_text_ports['email'].written
        assert fake_text_ports['telegram'].written == []

        # 9 minutes later, still below the 10 minute escalation threshold:
        # repeat a value change so _send_alert runs again, still no escalation
        fake_clock(9 * 60)
        alert.listen(MsgData(sensor.id, 31.0))
        assert fake_text_ports['telegram'].written == []

        # 11 minutes after alert start: escalation must have fired
        fake_clock(2 * 60)
        alert.listen(MsgData(sensor.id, 32.0))
        assert fake_text_ports['telegram'].written
        assert 'ESKALATION' in fake_text_ports['telegram'].written[-1]

        # escalation only fires once per active episode, not on every repeat
        escalation_count = len(fake_text_ports['telegram'].written)
        fake_clock(1 * 60)
        alert.listen(MsgData(sensor.id, 33.0))
        assert len(fake_text_ports['telegram'].written) == escalation_count

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)


def test_alert_escalation_resets_after_alert_clears(users_db_path, fake_text_ports, fake_clock):
    user_id = db.create_user(users_db_path, 'noah', 'pwd12345', role='viewer')
    db.set_current_users_db_path(users_db_path)
    try:
        db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email',
                                      escalation_channel='telegram', escalation_after_minutes=5)

        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), '', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        alert.listen(MsgData(sensor.id, 30.0))
        fake_clock(6 * 60)
        alert.listen(MsgData(sensor.id, 30.0))
        assert fake_text_ports['telegram'].written

        # alert clears
        alert.listen(MsgData(sensor.id, 10.0))
        assert alert._alert_since is None
        assert alert._escalated_users == set()

        fake_text_ports['telegram'].written.clear()

        # alert re-triggers: escalation must be possible again, but not
        # before the configured duration has elapsed a 2nd time
        alert.listen(MsgData(sensor.id, 30.0))
        assert fake_text_ports['telegram'].written == []

        fake_clock(6 * 60)
        alert.listen(MsgData(sensor.id, 31.0))
        assert fake_text_ports['telegram'].written

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)


def test_alert_no_escalation_when_channel_equals_primary(users_db_path, fake_text_ports, fake_clock):
    """ escalation_channel identical to the primary channel must not
        cause a duplicate send
    """
    user_id = db.create_user(users_db_path, 'olga', 'pwd12345', role='viewer')
    db.set_current_users_db_path(users_db_path)
    try:
        db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email',
                                      escalation_channel='email', escalation_after_minutes=1)

        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), '', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        alert.listen(MsgData(sensor.id, 30.0))
        fake_clock(5 * 60)
        alert.listen(MsgData(sensor.id, 31.0))

        assert [w for w in fake_text_ports['email'].written if 'ESKALATION' in w] == []

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)


def test_alert_no_escalation_when_disabled(users_db_path, fake_text_ports, fake_clock):
    user_id = db.create_user(users_db_path, 'pia', 'pwd12345', role='viewer')
    db.set_current_users_db_path(users_db_path)
    try:
        # escalation_after_minutes defaults to 0 -> disabled
        db.set_user_notification_pref(users_db_path, user_id, 'warnungen', 'email',
                                      escalation_channel='telegram')

        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), '', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        alert.listen(MsgData(sensor.id, 30.0))
        fake_clock(60 * 60)
        alert.listen(MsgData(sensor.id, 31.0))

        assert fake_text_ports['telegram'].written == []

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)

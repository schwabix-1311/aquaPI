#!/usr/bin/env python3
""" Tests for Step 28 (alarm escalation), reworked for the port-driven
    notification redesign: alert_escalation_config has one shared row per
    Alert node (not per-user - aquaPi's "users" are shared roles, not
    individual people) with 'escalation_channel'/'escalation_after_minutes';
    escalation_channel is a literal IoRegistry port name (e.g. 'Telegram
    #2'), not an 'email'/'telegram' enum, and Alert notifies that channel
    once an alert has stayed continuously active for at least that long -
    suppressed if it's the same port the alert's own primary 'port'
    already used.
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


# --- db.py: shared escalation config ---------------------------------------


def test_set_escalation_config_default_no_escalation(users_db_path):
    db.set_escalation_config(users_db_path, 'warnungen')

    configs = db.list_escalation_configs(users_db_path)
    assert configs == [{'alert_node_id': 'warnungen',
                        'escalation_channel': 'none', 'escalation_after_minutes': 0}]


def test_set_escalation_config_with_escalation(users_db_path):
    db.set_escalation_config(users_db_path, 'warnungen',
                             escalation_channel='Telegram #1', escalation_after_minutes=30)

    configs = db.list_escalation_configs(users_db_path)
    assert configs == [{'alert_node_id': 'warnungen',
                        'escalation_channel': 'Telegram #1', 'escalation_after_minutes': 30}]


def test_set_escalation_config_invalid_escalation_channel_raises(users_db_path):
    """ escalation_channel is a free-form IoRegistry port name now (not an
        enum), so the only remaining validation is "non-empty"
    """
    with pytest.raises(ValueError):
        db.set_escalation_config(users_db_path, 'warnungen', escalation_channel='')


def test_set_escalation_config_negative_escalation_minutes_raises(users_db_path):
    with pytest.raises(ValueError):
        db.set_escalation_config(users_db_path, 'warnungen',
                                 escalation_channel='Telegram #1',
                                 escalation_after_minutes=-1)


def test_get_escalation_config_includes_escalation_fields(users_db_path):
    db.set_escalation_config(users_db_path, 'warnungen',
                             escalation_channel='Telegram #1', escalation_after_minutes=15)

    config = db.get_escalation_config(users_db_path, 'warnungen')
    assert config['escalation_channel'] == 'Telegram #1'
    assert config['escalation_after_minutes'] == 15


def test_set_escalation_config_upserts_not_duplicates(users_db_path):
    """ setting the same alert node's config twice must update the single
        shared row, not add a 2nd one - this is the DB-layer guarantee
        that used to require deduping across multiple per-user rows
    """
    db.set_escalation_config(users_db_path, 'warnungen',
                             escalation_channel='Telegram #1', escalation_after_minutes=5)
    db.set_escalation_config(users_db_path, 'warnungen',
                             escalation_channel='Email #1', escalation_after_minutes=20)

    configs = db.list_escalation_configs(users_db_path)
    assert configs == [{'alert_node_id': 'warnungen',
                        'escalation_channel': 'Email #1', 'escalation_after_minutes': 20}]


def test_get_escalation_config_returns_none_when_unconfigured(users_db_path):
    assert db.get_escalation_config(users_db_path, 'nonexistent') is None


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
    """ register fake IoRegistry ports (arbitrary names, exactly like real
        Email/Telegram driver_factory ports) so Alert can send through
        them without any real network access. shareable=True mirrors the
        real DriverEmail/DriverTelegram ports (see DriverText.py) - their
        write() opens/sends/closes per call, so multiple Alert nodes may
        hold a claim on the same port concurrently.
    """
    names = ('Email #1', 'Telegram #1', 'Telegram #2')
    drivers = {name: _FakeTextDriver() for name in names}
    io_ports = {
        name: IoPort(PortFunc.Tout, lambda cfg, func, d=driver: d, {}, [],
                     shareable=True)
        for name, driver in drivers.items()
    }
    monkeypatch.setattr(IoRegistry, '_map', io_ports)
    return drivers


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
    db.set_current_users_db_path(users_db_path)
    try:
        db.set_escalation_config(users_db_path, 'warnungen',
                                 escalation_channel='Telegram #1', escalation_after_minutes=10)

        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Email #1', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        # alert starts, only the primary port gets notified
        alert.listen(MsgData(sensor.id, 30.0))
        assert fake_text_ports['Email #1'].written
        assert fake_text_ports['Telegram #1'].written == []

        # 9 minutes later, still below the 10 minute escalation threshold:
        # repeat a value change so _send_alert runs again, still no escalation
        fake_clock(9 * 60)
        alert.listen(MsgData(sensor.id, 31.0))
        assert fake_text_ports['Telegram #1'].written == []

        # 11 minutes after alert start: escalation must have fired
        fake_clock(2 * 60)
        alert.listen(MsgData(sensor.id, 32.0))
        assert fake_text_ports['Telegram #1'].written
        assert 'ESKALATION' in fake_text_ports['Telegram #1'].written[-1]

        # escalation only fires once per active episode, not on every repeat
        escalation_count = len(fake_text_ports['Telegram #1'].written)
        fake_clock(1 * 60)
        alert.listen(MsgData(sensor.id, 33.0))
        assert len(fake_text_ports['Telegram #1'].written) == escalation_count

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)


def test_alert_escalation_resets_after_alert_clears(users_db_path, fake_text_ports, fake_clock):
    db.set_current_users_db_path(users_db_path)
    try:
        db.set_escalation_config(users_db_path, 'warnungen',
                                 escalation_channel='Telegram #1', escalation_after_minutes=5)

        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Email #1', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        alert.listen(MsgData(sensor.id, 30.0))
        fake_clock(6 * 60)
        alert.listen(MsgData(sensor.id, 30.0))
        assert fake_text_ports['Telegram #1'].written

        # alert clears
        alert.listen(MsgData(sensor.id, 10.0))
        assert alert._alert_since is None
        assert alert._escalated is False

        fake_text_ports['Telegram #1'].written.clear()

        # alert re-triggers: escalation must be possible again, but not
        # before the configured duration has elapsed a 2nd time
        alert.listen(MsgData(sensor.id, 30.0))
        assert fake_text_ports['Telegram #1'].written == []

        fake_clock(6 * 60)
        alert.listen(MsgData(sensor.id, 31.0))
        assert fake_text_ports['Telegram #1'].written

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)


def test_alert_no_escalation_when_escalation_channel_equals_alert_port(
        users_db_path, fake_text_ports, fake_clock):
    """ escalation_channel identical to the firing Alert node's own
        primary port must not cause a duplicate send to that port
    """
    db.set_current_users_db_path(users_db_path)
    try:
        db.set_escalation_config(users_db_path, 'warnungen',
                                 escalation_channel='Email #1', escalation_after_minutes=1)

        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Email #1', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        alert.listen(MsgData(sensor.id, 30.0))
        fake_clock(5 * 60)
        alert.listen(MsgData(sensor.id, 31.0))

        assert [w for w in fake_text_ports['Email #1'].written if 'ESKALATION' in w] == []

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)


def test_alert_no_escalation_when_disabled(users_db_path, fake_text_ports, fake_clock):
    db.set_current_users_db_path(users_db_path)
    try:
        # escalation_after_minutes defaults to 0 -> disabled
        db.set_escalation_config(users_db_path, 'warnungen',
                                 escalation_channel='Telegram #1')

        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Email #1', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        alert.listen(MsgData(sensor.id, 30.0))
        fake_clock(60 * 60)
        alert.listen(MsgData(sensor.id, 31.0))

        assert fake_text_ports['Telegram #1'].written == []

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)


def test_alert_escalation_reaches_port_claimed_as_another_alerts_primary(
        users_db_path, fake_text_ports, fake_clock):
    """ Email/Telegram ports are shareable (see fake_text_ports): one
        Alert node's escalation_channel targeting 'Telegram #1' must
        still be delivered even while a 2nd, independent Alert node
        holds 'Telegram #1' as its own permanently-claimed primary
        port - previously this raised DriverPortInuseError and the
        escalation was silently dropped, see
        project_escalation_port_exclusivity memory
    """
    db.set_current_users_db_path(users_db_path)
    try:
        db.set_escalation_config(users_db_path, 'warnungen',
                                 escalation_channel='Telegram #1', escalation_after_minutes=5)

        bus = MsgBus(threaded=False)
        sensor = AnalogInput('Wasser', '', 25.0, '°C')
        sensor.plugin(bus)

        # 2nd, unrelated Alert node holds 'Telegram #1' as its own
        # primary port for its whole lifetime (PortDriverMixin)
        other_alert = Alert('Andere', AlertAbove(sensor.id, 40.0), 'Telegram #1', repeat=3600)
        other_alert.id = 'andere'
        other_alert.plugin(bus)

        alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Email #1', repeat=3600)
        alert.id = 'warnungen'
        alert.plugin(bus)

        alert.listen(MsgData(sensor.id, 30.0))
        fake_clock(6 * 60)
        alert.listen(MsgData(sensor.id, 31.0))

        assert [w for w in fake_text_ports['Telegram #1'].written if 'ESKALATION' in w]

        bus.teardown()
    finally:
        db.set_current_users_db_path(None)

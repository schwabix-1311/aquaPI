#!/usr/bin/env python3
""" Tests for machineroom/alert_nodes.py (Step 30): the basic alert
    conditions (AlertAbove/AlertBelow, threshold + duration logic) and
    the Alert node itself (name-fix regression, repeat throttling).
    Escalation (Step 28) already has dedicated coverage in
    test_alert_escalation.py.
"""

import operator

import pytest

from aquaPi.driver import IoRegistry, PortFunc, create_io_registry
from aquaPi.driver.base import IoPort, OutDriver
from aquaPi.machineroom.alert_nodes import (
    Alert, AlertAbove, AlertBelow, AlertThreshold)
from aquaPi.machineroom.in_nodes import AnalogInput
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.msg_types import MsgData


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


class _FakeTextDriver(OutDriver):
    """ minimal stand-in for a Tout driver, recording what was written """

    def __init__(self, cfg=None, func=PortFunc.Tout):
        super().__init__(cfg or {}, func)
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)


@pytest.fixture
def fake_alert_port(monkeypatch):
    driver = _FakeTextDriver()
    io_ports = {'Fake #1': IoPort(PortFunc.Tout, lambda cfg, func: driver, {}, [])}
    monkeypatch.setattr(IoRegistry, '_map', io_ports)
    return driver


@pytest.fixture
def fake_clock(monkeypatch):
    """ control the monotonic() clock seen by alert_nodes.py, so
        duration/repeat timing can be tested deterministically
    """
    state = {'now': 1000.0}

    def _monotonic():
        return state['now']

    import aquaPi.machineroom.alert_nodes as alert_nodes_mod
    monkeypatch.setattr(alert_nodes_mod, 'monotonic', _monotonic)

    def advance(seconds):
        state['now'] += seconds

    return advance


# --- AlertThreshold / AlertAbove / AlertBelow ------------------------------


def test_alert_above_triggers_when_value_reaches_limit():
    cond = AlertAbove('sensor', limit=26.0)

    assert cond.check_for_change(MsgData('sensor', 25.0), 'Wasser') is None
    assert cond.alerted is False

    assert cond.check_for_change(MsgData('sensor', 26.0), 'Wasser') is True
    assert cond.alerted is True


def test_alert_above_uses_ge_comparison():
    cond = AlertAbove('sensor', limit=26.0)
    assert cond._cmp is operator.ge


def test_alert_below_triggers_when_value_drops_to_limit():
    cond = AlertBelow('sensor', limit=10.0)

    assert cond.check_for_change(MsgData('sensor', 15.0), 'Wasser') is None
    assert cond.alerted is False

    assert cond.check_for_change(MsgData('sensor', 10.0), 'Wasser') is True
    assert cond.alerted is True


def test_alert_below_uses_le_comparison():
    cond = AlertBelow('sensor', limit=10.0)
    assert cond._cmp is operator.le


def test_alert_condition_ignores_messages_from_other_senders():
    cond = AlertAbove('sensor', limit=26.0)
    assert cond.check_for_change(MsgData('other', 99.0), 'Andere') is None
    assert cond.alerted is False


def test_alert_condition_clears_on_return_below_limit():
    cond = AlertAbove('sensor', limit=26.0)
    cond.check_for_change(MsgData('sensor', 30.0), 'Wasser')
    assert cond.alerted is True

    changed = cond.check_for_change(MsgData('sensor', 20.0), 'Wasser')
    assert changed is False
    assert cond.alerted is False


def test_alert_threshold_without_duration_triggers_instantly(fake_clock):
    cond = AlertThreshold('sensor', operator.ge, 'HOCH', limit=26.0, duration=0)
    assert cond.check_for_change(MsgData('sensor', 30.0), 'Wasser') is True


def test_alert_threshold_with_duration_delays_trigger(fake_clock):
    cond = AlertThreshold('sensor', operator.ge, 'HOCH', limit=26.0, duration=10)

    # limit exceeded, but duration not reached yet -> no alert
    changed = cond.check_for_change(MsgData('sensor', 30.0), 'Wasser')
    assert changed is None
    assert cond.alerted is False

    # 9 minutes later: still below the 10 minute duration
    fake_clock(9 * 60)
    changed = cond.check_for_change(MsgData('sensor', 31.0), 'Wasser')
    assert changed is None
    assert cond.alerted is False

    # 10 minutes after it started: now it must trigger
    fake_clock(1 * 60)
    changed = cond.check_for_change(MsgData('sensor', 32.0), 'Wasser')
    assert changed is True
    assert cond.alerted is True


def test_alert_threshold_with_duration_resets_when_condition_clears(fake_clock):
    cond = AlertThreshold('sensor', operator.ge, 'HOCH', limit=26.0, duration=10)

    cond.check_for_change(MsgData('sensor', 30.0), 'Wasser')
    fake_clock(5 * 60)
    # value drops below the limit again before duration elapsed
    cond.check_for_change(MsgData('sensor', 20.0), 'Wasser')
    assert cond._starttime is None

    # exceeding the limit again restarts the duration countdown from zero
    fake_clock(6 * 60)
    changed = cond.check_for_change(MsgData('sensor', 30.0), 'Wasser')
    assert changed is None
    assert cond.alerted is False


def test_alert_text_reports_ok_when_not_alerted():
    cond = AlertAbove('sensor', limit=26.0)
    cond.check_for_change(MsgData('sensor', 10.0), 'Wasser')
    assert 'OK' in cond.alert_text


def test_alert_text_reports_direction_and_limit_when_alerted():
    cond = AlertAbove('sensor', limit=26.0)
    cond.check_for_change(MsgData('sensor', 30.0), 'Wasser')
    assert 'HOCH' in cond.alert_text
    assert '26.00' in cond.alert_text
    assert 'Wasser' in cond.alert_text


# --- Alert node -------------------------------------------------------------


def test_alert_uses_sender_name_not_id_in_message(fake_alert_port):
    """ regression test for commit ab064bd ('alert messages now use
        names instead of ids'): the alert text must contain the human
        readable node name, not its lowercased/sanitized bus id.
    """
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser Temperatur', '', 25.0, '°C')
    sensor.plugin(bus)
    assert sensor.id != sensor.name  # id is a sanitized/lowercased form

    alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Fake #1')
    alert.plugin(bus)

    alert.listen(MsgData(sensor.id, 30.0))

    assert 'Wasser Temperatur' in alert.data[0]
    assert sensor.id not in alert.data[0]

    bus.teardown()


def test_alert_falls_back_to_id_for_unknown_sender_name(fake_alert_port):
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Fake #1')
    alert.plugin(bus)

    # simulate a message from an id the bus doesn't know an actual name for
    alert.listen(MsgData(sensor.id, 30.0))
    assert 'Wasser' in alert.data[0]

    bus.teardown()


def test_alert_sends_on_first_alert_and_on_recovery(fake_alert_port):
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Fake #1', repeat=3600)
    alert.plugin(bus)
    fake_alert_port.written.clear()

    alert.listen(MsgData(sensor.id, 30.0))
    assert len(fake_alert_port.written) == 1

    alert.listen(MsgData(sensor.id, 10.0))
    assert len(fake_alert_port.written) == 2

    bus.teardown()


def test_alert_does_not_resend_while_state_unchanged(fake_alert_port, fake_clock):
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Fake #1', repeat=3600)
    alert.plugin(bus)
    fake_alert_port.written.clear()

    alert.listen(MsgData(sensor.id, 30.0))
    assert len(fake_alert_port.written) == 1

    fake_clock(60)
    alert.listen(MsgData(sensor.id, 31.0))  # still alerted, same state -> no resend yet
    assert len(fake_alert_port.written) == 1

    bus.teardown()


def test_alert_repeats_after_repeat_interval_elapsed(fake_alert_port, fake_clock):
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    alert = Alert('Warnungen', AlertAbove(sensor.id, 26.0), 'Fake #1', repeat=600)
    alert.plugin(bus)
    fake_alert_port.written.clear()

    alert.listen(MsgData(sensor.id, 30.0))
    assert len(fake_alert_port.written) == 1

    fake_clock(300)
    alert.listen(MsgData(sensor.id, 31.0))
    assert len(fake_alert_port.written) == 1  # repeat interval not reached yet

    fake_clock(400)
    alert.listen(MsgData(sensor.id, 32.0))
    assert len(fake_alert_port.written) == 2  # repeat interval elapsed

    bus.teardown()


def test_alert_multiple_conditions_any_alert_true_if_one_active(fake_alert_port):
    bus = MsgBus(threaded=False)
    sensor1 = AnalogInput('Wasser', '', 25.0, '°C')
    sensor1.plugin(bus)
    sensor2 = AnalogInput('pH', '', 7.0, '')
    sensor2.plugin(bus)

    alert = Alert('Warnungen',
                  {AlertAbove(sensor1.id, 26.0), AlertBelow(sensor2.id, 6.0)},
                  'Fake #1')
    alert.plugin(bus)
    fake_alert_port.written.clear()

    alert.listen(MsgData(sensor1.id, 30.0))
    assert len(fake_alert_port.written) == 1
    assert 'HOCH' in fake_alert_port.written[-1]

    bus.teardown()


def test_alert_port_setter_rejects_non_output_driver(fake_alert_port):
    # 'Fake #1' is a Tout OutDriver, so a plain string port name that
    # doesn't resolve to any registered driver must just be ignored,
    # not raise - matching the existing log.error()-and-continue behavior
    alert = Alert('Warnungen', AlertAbove('sensor', 26.0), '')
    assert alert.port == ''
    assert alert._driver is None

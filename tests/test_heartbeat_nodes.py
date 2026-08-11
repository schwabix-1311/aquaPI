#!/usr/bin/env python3
""" Tests for the "silent-when-settled" fix: FadeCtrl/SunCtrl/UiInput
    periodically re-post their current value via the HeartbeatMixin mixin
    once settled, and SwitchDevice/AnalogDevice now post to the bus
    even when the incoming value is unchanged (previously only the
    hardware write was gated on change, silently dropping the post too).
"""

import time

import pytest

from aquaPi.driver import create_io_registry
from aquaPi.machineroom.ctrl_nodes import FadeCtrl, SunCtrl
from aquaPi.machineroom.in_nodes import UiAnalogInput, UiSwitchInput
from aquaPi.machineroom.msg_bus import BusListener, BusNode, BusRole, HeartbeatMixin, MsgBus
from aquaPi.machineroom.msg_types import MsgData
from aquaPi.machineroom.out_nodes import AnalogDevice, SwitchDevice


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


@pytest.fixture(autouse=True)
def _fast_heartbeat(monkeypatch):
    monkeypatch.setattr(HeartbeatMixin, 'HEARTBEAT_INTERVAL', 0.02)


class _Source(BusNode):
    ROLE = BusRole.IN_ENDP

    def __init__(self, name, value=0):
        super().__init__(name)
        self.data = value

    def get_settings(self):
        return []

    def emit(self, value):
        self.data = value
        self.post(MsgData(self.id, value))


class _Listener(BusListener):
    ROLE = BusRole.AUX

    def __init__(self, name, receives):
        super().__init__(name, receives=receives)
        self.received: list = []

    def listen(self, msg):
        super().listen(msg)
        if isinstance(msg, MsgData):
            self.received.append(msg.data)

    def get_settings(self):
        return []


@pytest.fixture
def bus():
    bus = MsgBus(threaded=False)
    yield bus
    bus.teardown()


@pytest.mark.parametrize('make_node', [
    lambda: FadeCtrl('Licht', 'wasser', fade_time=0, fade_out=0),
    lambda: SunCtrl('Licht', 'wasser', xscend=1),
    lambda: UiSwitchInput('Schalter'),
    lambda: UiAnalogInput('Regler'),
])
def test_settled_node_heartbeats_current_value(bus, make_node):
    node = make_node()
    node.plugin(bus)

    listener = _Listener('Verbraucher', receives=node.id)
    listener.plugin(bus)
    listener.received.clear()  # discard the initial state echo

    time.sleep(0.1)  # a handful of heartbeat intervals

    assert listener.received
    assert all(v == node.data for v in listener.received)

    node.pullout()


def test_heartbeat_stops_after_pullout(bus):
    node = UiSwitchInput('Schalter')
    node.plugin(bus)
    node.pullout()

    listener = _Listener('Verbraucher', receives=node.id)
    listener.plugin(bus)
    listener.received.clear()

    time.sleep(0.1)

    assert listener.received == []


def test_switch_device_posts_even_when_value_unchanged(bus):
    source = _Source('Quelle', value=0)
    source.plugin(bus)

    device = SwitchDevice('Relais', source.id, port='')
    device.plugin(bus)

    listener = _Listener('Beobachter', receives=device.id)
    listener.plugin(bus)
    listener.received.clear()

    source.emit(100)  # turns on - value changes
    source.emit(100)  # same value again - must still post to the bus

    assert listener.received == [100, 100]


def test_analog_device_posts_even_when_value_unchanged(bus):
    source = _Source('Quelle', value=0)
    source.plugin(bus)

    device = AnalogDevice('Dimmer', source.id, port='')
    device.plugin(bus)

    listener = _Listener('Beobachter', receives=device.id)
    listener.plugin(bus)
    listener.received.clear()

    source.emit(50.0)
    source.emit(50.0)  # same value again - must still post to the bus

    assert listener.received == [50.0, 50.0]

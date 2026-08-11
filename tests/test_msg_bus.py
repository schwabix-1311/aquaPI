#!/usr/bin/env python3
""" Example tests for machineroom/msg_bus.py (Step 29): node
    registration/plugin/pullout and message forwarding between nodes.
    These are meant as a starting-point reference for the pytest
    infrastructure introduced in this step, not full coverage - see
    Step 30 for a broader test suite of the core components.
"""

import time

import pytest

from aquaPi.machineroom.msg_bus import BusNode, BusListener, BusRole, HeartbeatMixin, MsgBus
from aquaPi.machineroom.msg_types import MsgData


class _DummySource(BusNode):
    """ minimal concrete BusNode: just posts whatever value it's given """
    ROLE = BusRole.IN_ENDP

    def __init__(self, name, value=0):
        super().__init__(name)
        self.data = value

    def get_settings(self):
        return []

    def emit(self, value):
        self.data = value
        self.post(MsgData(self.id, value))


class _DummyListener(BusListener):
    """ minimal concrete BusListener: records every MsgData it receives """
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


class _DummyHeartbeatSource(HeartbeatMixin, BusNode):
    """ minimal concrete BusNode using the HeartbeatMixin mixin, matching how
        FadeCtrl/SunCtrl/UiInput wire it up in plugin()/pullout()
    """
    ROLE = BusRole.IN_ENDP
    HEARTBEAT_INTERVAL = 0.02

    def __init__(self, name, value=0):
        super().__init__(name)
        self.data = value

    def get_settings(self):
        return []

    def plugin(self, bus):
        super().plugin(bus)
        self._start_heartbeat()

    def pullout(self):
        self._stop_heartbeat()
        return super().pullout()


@pytest.fixture
def bus():
    bus = MsgBus(threaded=False)
    yield bus
    bus.teardown()


def test_plugin_registers_node_on_bus(bus):
    source = _DummySource('Quelle')
    assert source not in bus.nodes

    source.plugin(bus)

    assert source in bus.nodes
    assert bus.get_node('quelle') is source
    assert bus.get_node('Quelle') is source


def test_plugin_rejects_duplicate_id(bus):
    _DummySource('Quelle').plugin(bus)
    with pytest.raises(Exception):
        _DummySource('Quelle').plugin(bus)


def test_pullout_unregisters_node(bus):
    source = _DummySource('Quelle')
    source.plugin(bus)

    result = source.pullout()

    assert result is True
    assert source not in bus.nodes
    assert bus.get_node('quelle') is None


def test_pullout_without_plugin_returns_false():
    source = _DummySource('Quelle')
    assert source.pullout() is False


def test_message_is_forwarded_to_listening_node(bus):
    source = _DummySource('Quelle')
    source.plugin(bus)

    listener = _DummyListener('Verbraucher', receives=source.id)
    listener.plugin(bus)
    # BusNode.listen() already echoes the source's current value once a new
    # listener subscribes to it (MsgHello handling) - not part of what this
    # test wants to verify, so it's cleared before triggering a real change
    listener.received.clear()

    source.emit(42.0)

    assert listener.received == [42.0]


def test_message_is_not_forwarded_to_non_listening_node(bus):
    source = _DummySource('Quelle')
    source.plugin(bus)
    other = _DummySource('Andere')
    other.plugin(bus)

    listener = _DummyListener('Verbraucher', receives=source.id)
    listener.plugin(bus)
    listener.received.clear()  # discard the initial state echo from 'source'

    other.emit(7.0)

    assert listener.received == []


def test_wildcard_receives_forwards_all_messages(bus):
    source = _DummySource('Quelle')
    source.plugin(bus)

    listener = _DummyListener('Verbraucher', receives='*')
    listener.plugin(bus)

    source.emit(1.0)
    source.emit(2.0)

    assert listener.received == [1.0, 2.0]


def test_get_nodes_filters_by_role(bus):
    source = _DummySource('Quelle')
    source.plugin(bus)
    listener = _DummyListener('Verbraucher', receives=source.id)
    listener.plugin(bus)

    assert bus.get_nodes(roles={BusRole.IN_ENDP}) == [source]
    assert bus.get_nodes(roles={BusRole.AUX}) == [listener]
    assert set(bus.get_nodes()) == {source, listener}


def test_heartbeat_reposts_unchanged_value_while_plugged_in(bus):
    source = _DummyHeartbeatSource('Quelle', value=42.0)
    source.plugin(bus)

    listener = _DummyListener('Verbraucher', receives=source.id)
    listener.plugin(bus)
    listener.received.clear()  # discard the initial state echo

    time.sleep(0.1)  # a handful of heartbeat intervals

    assert listener.received
    assert all(v == 42.0 for v in listener.received)


def test_heartbeat_stops_after_pullout(bus):
    source = _DummyHeartbeatSource('Quelle', value=1.0)
    source.plugin(bus)
    source.pullout()

    listener = _DummyListener('Verbraucher', receives=source.id)
    listener.plugin(bus)
    listener.received.clear()

    time.sleep(0.1)

    assert listener.received == []

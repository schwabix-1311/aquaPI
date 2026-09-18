#!/usr/bin/env python3
""" Tests for machineroom/aux_nodes.py: StdDevAux, the rolling-standard-
    deviation node used to flag reduced water flow via increased
    temperature volatility (see ROADMAP.md).
"""

import statistics

import pytest

from aquaPi.driver import create_io_registry
from aquaPi.machineroom.aux_nodes import StdDevAux
from aquaPi.machineroom.in_nodes import AnalogInput
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.msg_types import MsgData


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


@pytest.fixture
def fake_clock(monkeypatch):
    """ control the monotonic() clock seen by aux_nodes.py, so window
        eviction can be tested deterministically
    """
    state = {'now': 1000.0}

    def _monotonic():
        return state['now']

    import aquaPi.machineroom.aux_nodes as aux_nodes_mod
    monkeypatch.setattr(aux_nodes_mod, 'monotonic', _monotonic)

    def advance(seconds):
        state['now'] += seconds

    return advance


def _feed(node, values, advance=None, step=0):
    for v in values:
        if advance and step:
            advance(step)
        node.listen(MsgData('sensor', v))


def test_no_output_before_min_samples(fake_clock):
    node = StdDevAux('StdDev', 'sensor')
    for v in (25.0, 25.1, 25.0, 24.9):  # one short of _MIN_SAMPLES (5)
        node.listen(MsgData('sensor', v))
    assert node.data == -1


def test_output_matches_pstdev_of_window(fake_clock):
    node = StdDevAux('StdDev', 'sensor', window=3600)
    values = [25.0, 25.1, 25.0, 24.9, 25.05, 24.95]
    _feed(node, values, fake_clock, step=10)
    assert node.data == round(statistics.pstdev(values), 4)


def test_old_samples_are_evicted_from_window(fake_clock):
    node = StdDevAux('StdDev', 'sensor', window=100)

    # 5 samples, 10s apart, well within the 100s window
    _feed(node, [25.0, 25.0, 25.0, 25.0, 25.0], fake_clock, step=10)
    assert node.data == 0.0

    # advance well past the window, then feed a single noisy burst -
    # only the burst should remain in the window
    fake_clock(200)
    burst = [24.0, 26.0, 24.0, 26.0, 24.0]
    _feed(node, burst, fake_clock, step=1)
    assert node.data == round(statistics.pstdev(burst), 4)


def test_low_stddev_stays_after_high_variance_leaves_window(fake_clock):
    node = StdDevAux('StdDev', 'sensor', window=60)

    # noisy burst, all inside the window at first
    _feed(node, [20.0, 30.0, 20.0, 30.0, 20.0], fake_clock, step=1)
    assert node.data > 1.0

    # let the noisy burst fully age out, then feed a quiet run
    fake_clock(120)
    quiet = [25.0, 25.0, 25.0, 25.0, 25.0]
    _feed(node, quiet, fake_clock, step=1)
    assert node.data == 0.0


def test_ignores_non_data_messages(fake_clock):
    from aquaPi.machineroom.msg_types import MsgHello

    node = StdDevAux('StdDev', 'sensor')
    node.listen(MsgHello('sensor'))
    assert node.data == -1


def test_state_round_trip_preserves_window(fake_clock):
    node = StdDevAux('StdDev', 'sensor', window=1800)
    state = node.__getstate__()
    assert state['window'] == 1800

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)
    assert restored.window == 1800
    assert restored.receives == ['sensor']


def test_data_range_is_analog_without_receiving_data():
    # unlike AvgAux/MinAux/MaxAux (whose data_range only becomes numeric
    # once they've actually received data), StdDevAux must be immediately
    # selectable as an AlertCond target in an unsaved /wiring draft
    from aquaPi.machineroom.msg_bus import DataRange
    assert StdDevAux.data_range == DataRange.ANALOG


def test_produces_its_source_unit():
    # a standard deviation of a °C signal is itself in °C - inherit the
    # source's unit rather than leaving it unitless (BusNode's default)
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    node = StdDevAux('StdDev', sensor.id)
    node.plugin(bus)

    assert node.__getstate__()['unit'] == '°C'
    bus.teardown()


def test_scale_multiplies_output(fake_clock):
    node = StdDevAux('StdDev', 'sensor', window=3600, scale=100)
    values = [25.0, 25.1, 25.0, 24.9, 25.05, 24.95]
    _feed(node, values, fake_clock, step=10)
    assert node.data == round(statistics.pstdev(values) * 100, 4)


def test_scale_other_than_one_reports_percent_unit():
    # not a rigorous percentage (no fixed 0-100 denominator) - just what
    # routes it onto the dashboard's dedicated axis instead of the one
    # shared (and auto-scaled) with its much-larger-magnitude source
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    default_scale = StdDevAux('StdDev', sensor.id)
    default_scale.plugin(bus)
    assert default_scale.__getstate__()['unit'] == '°C'

    scaled = StdDevAux('StdDevScaled', sensor.id, scale=100)
    scaled.plugin(bus)
    assert scaled.__getstate__()['unit'] == '%'

    bus.teardown()


def test_state_round_trip_preserves_scale(fake_clock):
    node = StdDevAux('StdDev', 'sensor', scale=50)
    state = node.__getstate__()
    assert state['scale'] == 50

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)
    assert restored.scale == 50


def test_state_round_trip_defaults_scale_for_pre_existing_saved_nodes(fake_clock):
    # a node saved before 'scale' existed has no such key in its state
    node = StdDevAux('StdDev', 'sensor')
    state = node.__getstate__()
    del state['scale']

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)
    assert restored.scale == 1.0

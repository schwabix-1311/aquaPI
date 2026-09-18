#!/usr/bin/env python3
""" Tests for machineroom/aux_nodes.py: StdDevAux, the rolling-standard-
    deviation node used to flag reduced water flow via increased
    temperature volatility (see ROADMAP.md).
"""

import statistics

import pytest

from aquaPi.machineroom.aux_nodes import StdDevAux
from aquaPi.machineroom.msg_types import MsgData


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

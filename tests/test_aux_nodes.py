#!/usr/bin/env python3
""" Tests for machineroom/aux_nodes.py: StdDevAux, the sample-count
    standard-deviation node used to flag reduced water flow via
    increased temperature volatility (see ROADMAP.md).
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


def _feed(node, values):
    for v in values:
        node.listen(MsgData('sensor', v))


def test_no_output_before_enough_samples():
    node = StdDevAux('StdDev', 'sensor', samples=5)
    _feed(node, [25.0, 25.1, 25.0, 24.9])   # one short of 5
    assert node.data == -1


def test_output_matches_pstdev_of_last_n_samples():
    node = StdDevAux('StdDev', 'sensor', samples=5)
    values = [25.0, 25.1, 25.0, 24.9, 25.05]
    _feed(node, values)
    assert node.data == round(statistics.pstdev(values), 4)


def test_older_samples_drop_out_once_full():
    node = StdDevAux('StdDev', 'sensor', samples=3)

    _feed(node, [25.0, 25.0, 25.0])
    assert node.data == 0.0

    # 3 more, very different values - only the last 3 of the 6 fed total
    # should count, not all 6
    burst = [10.0, 20.0, 30.0]
    _feed(node, burst)
    assert node.data == round(statistics.pstdev(burst), 4)


def test_low_stddev_after_high_variance_scrolls_out():
    node = StdDevAux('StdDev', 'sensor', samples=5)

    _feed(node, [20.0, 30.0, 20.0, 30.0, 20.0])
    assert node.data > 1.0

    quiet = [25.0, 25.0, 25.0, 25.0, 25.0]
    _feed(node, quiet)
    assert node.data == 0.0


def test_ignores_non_data_messages():
    from aquaPi.machineroom.msg_types import MsgHello

    node = StdDevAux('StdDev', 'sensor')
    node.listen(MsgHello('sensor'))
    assert node.data == -1


def test_reader_speed_never_blocks_output():
    # the bug that prompted switching from a time window to a sample
    # count: a source polling slower than the old time window allowed
    # could never accumulate enough samples before the oldest aged back
    # out - permanently, not just slower. A sample count has no such
    # failure mode: feeding samples one at a time (however far apart in
    # real time, which this test doesn't even need to simulate) always
    # eventually reaches `samples`.
    node = StdDevAux('StdDev', 'sensor', samples=5)
    values = [24.9, 25.0, 25.1, 25.0, 24.95]
    for v in values:
        node.listen(MsgData('sensor', v))
    assert node.data == round(statistics.pstdev(values), 4)


def test_state_round_trip_preserves_samples():
    node = StdDevAux('StdDev', 'sensor', samples=10)
    state = node.__getstate__()
    assert state['samples'] == 10

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)
    assert restored.samples == 10
    assert restored.receives == ['sensor']


def test_state_round_trip_defaults_samples_for_pre_migration_saved_nodes():
    # a node saved before 'samples' existed (the old time-windowed
    # 'window' Setting) has no 'samples' key at all - must fall back to
    # the schema default, not error or misinterpret the old value
    node = StdDevAux('StdDev', 'sensor')
    state = node.__getstate__()
    del state['samples']
    state['window'] = 3600   # what an old saved node's state looked like

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)
    assert restored.samples == 30


def test_samples_coerces_a_float_to_int():
    # regression test: every 'number'-type Setting travels the wire as a
    # float (api.py's _validate_and_cast), and a live /wiring or
    # /settings edit sets 'samples' via plain setattr(), bypassing
    # build_node()'s own int() cast entirely - persisting that float and
    # restoring it crashed deque(maxlen=<float>) in production
    node = StdDevAux('StdDev', 'sensor', samples=20.0)
    assert node.samples == 20
    assert isinstance(node.samples, int)
    assert node._values.maxlen == 20

    node.samples = 15.0   # simulates a live setattr() from an edit
    assert node.samples == 15
    assert isinstance(node.samples, int)


def test_growing_samples_live_does_not_permanently_stop_output():
    # regression test for the exact production incident: deque.maxlen is
    # fixed at construction, so a live edit that only updated the stored
    # count (not the deque) left a too-small deque in place - growing
    # 'samples' this way made len(self._values) >= self.samples
    # permanently unsatisfiable, silently killing the node forever
    # (observed: StdDevAux stopped posting for 22+ hours after exactly
    # this kind of edit, until the process was restarted)
    node = StdDevAux('StdDev', 'sensor', samples=5)
    values = [24.9, 25.0, 25.1, 25.0, 24.95]
    _feed(node, values)
    assert node.data == round(statistics.pstdev(values), 4)   # ready

    node.samples = 10   # live edit, growing past the original maxlen=5
    assert node._values.maxlen == 10

    # without the fix, len(self._values) could never reach 10 again -
    # feed exactly enough new readings to prove it actually can now
    more = [24.9, 25.05, 25.1, 24.95, 25.0]
    _feed(node, more)
    all_ten = values + more
    assert node.data == round(statistics.pstdev(all_ten), 4)


def test_shrinking_samples_live_takes_effect_immediately():
    node = StdDevAux('StdDev', 'sensor', samples=10)
    values = [24.9, 25.0, 25.1, 25.0, 24.95, 25.05, 24.85, 25.15, 25.0, 24.9]
    _feed(node, values)
    assert node._values.maxlen == 10

    node.samples = 5   # live edit, shrinking
    assert node._values.maxlen == 5
    # the shrink itself trims to the last 5 items already held - the
    # very next reading should reflect a 5-sample window, not wait for
    # 5 brand new readings to arrive
    node.listen(MsgData('sensor', 24.7))
    expected = values[-4:] + [24.7]
    assert node.data == round(statistics.pstdev(expected), 4)


def test_state_round_trip_survives_a_float_samples_value():
    # simulates a node that was live-edited (setattr with a float, see
    # above) then saved - its persisted state has samples as a float
    node = StdDevAux('StdDev', 'sensor', samples=10)
    state = node.__getstate__()
    state['samples'] = 20.0

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)   # must not raise
    assert restored.samples == 20
    assert isinstance(restored.samples, int)


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


def test_scale_multiplies_output():
    node = StdDevAux('StdDev', 'sensor', samples=5, scale=100)
    values = [25.0, 25.1, 25.0, 24.9, 25.05]
    _feed(node, values)
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


def test_state_round_trip_preserves_scale():
    node = StdDevAux('StdDev', 'sensor', scale=50)
    state = node.__getstate__()
    assert state['scale'] == 50

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)
    assert restored.scale == 50


def test_state_round_trip_defaults_scale_for_pre_existing_saved_nodes():
    # a node saved before 'scale' existed has no such key in its state
    node = StdDevAux('StdDev', 'sensor')
    state = node.__getstate__()
    del state['scale']

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)
    assert restored.scale == 1.0


def test_auto_scale_calibrates_once_from_first_window():
    node = StdDevAux('StdDev', 'sensor', samples=5, auto_scale=True)
    values = [24.9, 25.0, 25.1, 25.0, 24.95]
    _feed(node, values)

    raw = statistics.pstdev(values)
    assert node.scale == round(StdDevAux._AUTO_SCALE_TARGET / raw, 4)
    assert node.data == round(raw * node.scale, 4)


def test_auto_scale_does_not_recalibrate_on_later_windows():
    node = StdDevAux('StdDev', 'sensor', samples=3, auto_scale=True)
    _feed(node, [24.9, 25.0, 25.1])
    calibrated_scale = node.scale

    # a much noisier later window must NOT shift the scale again - a
    # continuously-adapting scale would silently normalize away exactly
    # the kind of change this node exists to surface
    _feed(node, [10.0, 40.0, 10.0])
    assert node.scale == calibrated_scale


def test_constructing_with_auto_scale_true_does_not_clear_an_explicit_scale():
    # __init__ (a fresh create, or __setstate__ restoring a previously-
    # calibrated node) must bypass the "clear on enable" side effect -
    # only a live re-toggle on an already-running node should reset it
    node = StdDevAux('StdDev', 'sensor', scale=50, auto_scale=True)
    assert node.scale == 50


def test_live_reenable_of_auto_scale_clears_stale_scale():
    # simulates what apply_config_diff's update path does to an existing
    # live node: setattr(node, 'auto_scale', True) - not a fresh __init__
    node = StdDevAux('StdDev', 'sensor', samples=3, scale=99, auto_scale=False)
    _feed(node, [24.9, 25.0, 25.1])   # some stale state accumulated
    assert node.scale == 99   # untouched while auto_scale is off

    node.auto_scale = True   # live re-toggle, via the property setter
    assert node.scale == 1.0
    assert node._calibrated is False

    # and it then calibrates normally on the next reading
    node.listen(MsgData('sensor', 30.0))
    assert node.scale != 1.0
    assert node._calibrated is True


def test_toggling_auto_scale_off_leaves_the_calibrated_scale_alone():
    node = StdDevAux('StdDev', 'sensor', samples=3, auto_scale=True)
    _feed(node, [24.9, 25.0, 25.1])
    calibrated_scale = node.scale

    node.auto_scale = False
    assert node.scale == calibrated_scale


def test_auto_scale_retries_after_a_perfectly_flat_first_window():
    node = StdDevAux('StdDev', 'sensor', samples=3, auto_scale=True)

    _feed(node, [25.0, 25.0, 25.0])   # raw stddev 0.0 - can't calibrate from
    assert node.scale == 1.0
    assert node._calibrated is False

    _feed(node, [24.0, 26.0, 24.0])   # next window has real variance
    assert node.scale != 1.0
    assert node._calibrated is True


def test_auto_scale_off_leaves_scale_at_whatever_was_set():
    node = StdDevAux('StdDev', 'sensor', samples=3, scale=42, auto_scale=False)
    _feed(node, [24.9, 25.0, 25.1])
    assert node.scale == 42


def test_state_round_trip_preserves_auto_scale():
    node = StdDevAux('StdDev', 'sensor', auto_scale=True)
    state = node.__getstate__()
    assert state['auto_scale'] is True

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)
    assert restored.auto_scale is True


def test_state_round_trip_defaults_auto_scale_for_pre_existing_saved_nodes():
    # a node saved before 'auto_scale' existed has no such key in its state
    node = StdDevAux('StdDev', 'sensor')
    state = node.__getstate__()
    del state['auto_scale']

    restored = StdDevAux.__new__(StdDevAux)
    restored.__setstate__(state)
    assert restored.auto_scale is False

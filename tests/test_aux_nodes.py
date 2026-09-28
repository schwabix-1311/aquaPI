#!/usr/bin/env python3
""" Tests for machineroom/aux_nodes.py: VolatilityAux, the sample-count
    standard-deviation/variance node used to flag reduced water flow via
    increased temperature volatility (see ROADMAP.md).
"""

import statistics
import time

import pytest

from aquaPi import db as db_module
from aquaPi.driver import create_io_registry
from aquaPi.machineroom.aux_nodes import VolatilityAux
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
    node = VolatilityAux('StdDev', 'sensor', samples=5)
    _feed(node, [25.0, 25.1, 25.0, 24.9])   # one short of 5
    assert node.data == -1


def test_output_matches_pstdev_of_last_n_samples():
    node = VolatilityAux('StdDev', 'sensor', samples=5)
    values = [25.0, 25.1, 25.0, 24.9, 25.05]
    _feed(node, values)
    assert node.data == round(statistics.pstdev(values), 4)


def test_older_samples_drop_out_once_full():
    node = VolatilityAux('StdDev', 'sensor', samples=3)

    _feed(node, [25.0, 25.0, 25.0])
    assert node.data == 0.0

    # 3 more, very different values - only the last 3 of the 6 fed total
    # should count, not all 6
    burst = [10.0, 20.0, 30.0]
    _feed(node, burst)
    assert node.data == round(statistics.pstdev(burst), 4)


def test_low_stddev_after_high_variance_scrolls_out():
    node = VolatilityAux('StdDev', 'sensor', samples=5)

    _feed(node, [20.0, 30.0, 20.0, 30.0, 20.0])
    assert node.data > 1.0

    quiet = [25.0, 25.0, 25.0, 25.0, 25.0]
    _feed(node, quiet)
    assert node.data == 0.0


def test_ignores_non_data_messages():
    from aquaPi.machineroom.msg_types import MsgHello

    node = VolatilityAux('StdDev', 'sensor')
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
    node = VolatilityAux('StdDev', 'sensor', samples=5)
    values = [24.9, 25.0, 25.1, 25.0, 24.95]
    for v in values:
        node.listen(MsgData('sensor', v))
    assert node.data == round(statistics.pstdev(values), 4)


def test_state_round_trip_preserves_samples():
    node = VolatilityAux('StdDev', 'sensor', samples=10)
    state = node.__getstate__()
    assert state['samples'] == 10

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored.samples == 10
    assert restored.receives == ['sensor']


def test_state_round_trip_defaults_samples_for_pre_migration_saved_nodes():
    # a node saved before 'samples' existed (the old time-windowed
    # 'window' Setting) has no 'samples' key at all - must fall back to
    # the schema default, not error or misinterpret the old value
    node = VolatilityAux('StdDev', 'sensor')
    state = node.__getstate__()
    del state['samples']
    state['window'] = 3600   # what an old saved node's state looked like

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored.samples == 30


def test_samples_coerces_a_float_to_int():
    # regression test: every 'number'-type Setting travels the wire as a
    # float (api.py's _validate_and_cast), and a live /wiring or
    # /settings edit sets 'samples' via plain setattr(), bypassing
    # build_node()'s own int() cast entirely - persisting that float and
    # restoring it crashed deque(maxlen=<float>) in production
    node = VolatilityAux('StdDev', 'sensor', samples=20.0)
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
    # (observed: VolatilityAux stopped posting for 22+ hours after exactly
    # this kind of edit, until the process was restarted)
    node = VolatilityAux('StdDev', 'sensor', samples=5)
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
    node = VolatilityAux('StdDev', 'sensor', samples=10)
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
    node = VolatilityAux('StdDev', 'sensor', samples=10)
    state = node.__getstate__()
    state['samples'] = 20.0

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)   # must not raise
    assert restored.samples == 20
    assert isinstance(restored.samples, int)


def test_data_range_is_analog_without_receiving_data():
    # unlike AvgAux/MinAux/MaxAux (whose data_range only becomes numeric
    # once they've actually received data), VolatilityAux must be immediately
    # selectable as an AlertCond target in an unsaved /wiring draft
    from aquaPi.machineroom.msg_bus import DataRange
    assert VolatilityAux.data_range == DataRange.ANALOG


def test_legacy_stddevaux_type_name_still_loads():
    # this class was renamed from StdDevAux - a wiring.sqlite row saved
    # under the old name (type_name literally 'StdDevAux' in the DB)
    # must still deserialize, via db.LEGACY_TYPE_ALIASES, not raise
    # "Unknown node type in database"
    node = VolatilityAux('StdDev', 'sensor', samples=5, scale=42)
    state = node.__getstate__()

    restored = db_module._deserialize_node('StdDevAux', state)
    assert isinstance(restored, VolatilityAux)
    assert restored.scale == 42

    # and it self-heals: re-serializing (what any save does) now reports
    # the current name, not the stale one it was loaded under
    assert type(restored).__name__ == 'VolatilityAux'


def test_legacy_stddevaux_alias_is_not_offered_as_a_creatable_type():
    # get_node_type_schema() drives /wiring's "add node" list - it must
    # only ever list the current name, not a stale duplicate entry
    schema = db_module.get_node_type_schema()
    assert 'VolatilityAux' in schema
    assert 'StdDevAux' not in schema


def test_produces_its_source_unit():
    # a standard deviation of a °C signal is itself in °C - inherit the
    # source's unit rather than leaving it unitless (BusNode's default)
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    node = VolatilityAux('StdDev', sensor.id)
    node.plugin(bus)

    assert node.__getstate__()['unit'] == '°C'
    bus.teardown()


def test_scale_multiplies_output():
    node = VolatilityAux('StdDev', 'sensor', samples=5, scale=100)
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

    default_scale = VolatilityAux('StdDev', sensor.id)
    default_scale.plugin(bus)
    assert default_scale.__getstate__()['unit'] == '°C'

    scaled = VolatilityAux('StdDevScaled', sensor.id, scale=100)
    scaled.plugin(bus)
    assert scaled.__getstate__()['unit'] == '%'

    bus.teardown()


def test_state_round_trip_preserves_scale():
    node = VolatilityAux('StdDev', 'sensor', scale=50)
    state = node.__getstate__()
    assert state['scale'] == 50

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored.scale == 50


def test_state_round_trip_defaults_scale_for_pre_existing_saved_nodes():
    # a node saved before 'scale' existed has no such key in its state
    node = VolatilityAux('StdDev', 'sensor')
    state = node.__getstate__()
    del state['scale']

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored.scale == 1.0


def test_metric_defaults_to_stddev():
    node = VolatilityAux('StdDev', 'sensor', samples=5)
    values = [24.9, 25.0, 25.1, 25.0, 24.95]
    _feed(node, values)
    assert node.data == round(statistics.pstdev(values), 4)


def test_metric_variance_computes_pvariance_instead_of_stddev():
    node = VolatilityAux('StdDev', 'sensor', samples=5, metric='variance')
    values = [24.9, 25.0, 25.1, 25.0, 24.95]
    _feed(node, values)
    assert node.data == round(statistics.pvariance(values), 4)


def test_variance_unit_gets_squared_suffix_when_unscaled():
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    node = VolatilityAux('StdDev', sensor.id, metric='variance')
    node.plugin(bus)

    assert node.__getstate__()['unit'] == '°C²'
    bus.teardown()


def test_live_metric_switch_rearms_auto_scale():
    # a scale calibrated for stddev is meaningless for variance's very
    # different numeric range - switching must not silently keep it
    node = VolatilityAux('StdDev', 'sensor', samples=3, auto_scale=True)
    _feed(node, [24.9, 25.0, 25.1])
    node._calib_start = time.time() - VolatilityAux._AUTO_SCALE_DURATION - 1
    node.listen(MsgData('sensor', 25.05))
    assert node._calibrated is True

    node.metric = 'variance'   # live edit, via the property setter
    assert node.scale == 1.0
    assert node._calibrated is False
    assert node._calib_samples == []


def test_live_metric_switch_leaves_manual_scale_alone():
    # auto_scale is off - the user is in charge of scale, a metric
    # switch shouldn't silently reset it
    node = VolatilityAux('StdDev', 'sensor', scale=42, auto_scale=False)
    node.metric = 'variance'
    assert node.scale == 42


def test_state_round_trip_preserves_metric():
    node = VolatilityAux('StdDev', 'sensor', metric='variance')
    state = node.__getstate__()
    assert state['metric'] == 'variance'

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored.metric == 'variance'


def test_state_round_trip_defaults_metric_for_pre_existing_saved_nodes():
    # a node saved before 'metric' existed has no such key in its state
    node = VolatilityAux('StdDev', 'sensor')
    state = node.__getstate__()
    del state['metric']

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored.metric == 'stddev'


def test_auto_scale_does_not_calibrate_before_duration_elapses():
    node = VolatilityAux('StdDev', 'sensor', samples=3, auto_scale=True)
    _feed(node, [24.9, 25.0, 25.1, 24.8, 25.2])   # several windows' worth
    assert node._calibrated is False
    assert node.scale == 1.0
    assert len(node._calib_samples) > 0   # accumulating, just not finished


def test_calib_remaining_seconds_counts_down_while_calibrating():
    node = VolatilityAux('StdDev', 'sensor', samples=3, auto_scale=True)
    node._calib_start = time.time() - 3600   # 1h into the 24h window
    _feed(node, [24.9, 25.0, 25.1])
    state = node.__getstate__()
    assert state['calibrating'] is True
    remaining = state['calib_remaining_seconds']
    # ~23h left - generous bounds against test-run timing jitter
    assert 23 * 3600 - 5 < remaining < 23 * 3600 + 5


def test_calib_remaining_seconds_is_none_once_calibrated():
    node = VolatilityAux('StdDev', 'sensor', samples=3, auto_scale=True)
    _feed(node, [24.9, 25.0, 25.1])
    node._calib_start = time.time() - VolatilityAux._AUTO_SCALE_DURATION - 1
    node.listen(MsgData('sensor', 25.05))   # completes calibration
    assert node._calibrated is True

    state = node.__getstate__()
    assert state['calibrating'] is False
    assert state['calib_remaining_seconds'] is None


def test_calib_remaining_seconds_is_none_before_the_clock_starts():
    # e.g. right after loading an old pre-24h-design save with auto_scale
    # on but no persisted calib_start (see the setstate default-for-pre-
    # existing-saved-nodes tests below) - nothing to count down from yet
    node = VolatilityAux('StdDev', 'sensor', auto_scale=True)
    node._calib_start = None
    state = node.__getstate__()
    assert state['calibrating'] is True
    assert state['calib_remaining_seconds'] is None


def test_auto_scale_calibrates_from_p90_once_duration_elapses():
    node = VolatilityAux('StdDev', 'sensor', samples=2, auto_scale=True)
    # samples=2 makes each window's raw stddev = |a-b|/2 - feeding this
    # sequence produces exactly the raw stddevs 0.1, 0.2, ..., 1.0 in
    # order (one per consecutive pair)
    values = [0, 0.2, -0.2, 0.4, -0.4, 0.6, -0.6, 0.8, -0.8, 1.0, -1.0]
    _feed(node, values)
    assert node._calibrated is False   # duration hasn't elapsed yet

    # simulate the full calibration duration having already elapsed
    node._calib_start = time.time() - VolatilityAux._AUTO_SCALE_DURATION - 1
    node.listen(MsgData('sensor', 1.2))   # 11th window, raw stddev 1.1 -> triggers finish

    assert node._calibrated is True
    # p90 of [0.1, 0.2, ..., 1.1] (11 values, linear interpolation) lands
    # exactly on 1.0 (index 0.9*10 = 9.0, no interpolation needed)
    assert node.scale == pytest.approx(round(VolatilityAux._AUTO_SCALE_TARGET / 1.0, 4))
    assert node._calib_samples == []   # cleared once calibration completes


def test_auto_scale_does_not_recalibrate_after_completing():
    node = VolatilityAux('StdDev', 'sensor', samples=3, auto_scale=True)
    _feed(node, [24.9, 25.0, 25.1])
    node._calib_start = time.time() - VolatilityAux._AUTO_SCALE_DURATION - 1
    node.listen(MsgData('sensor', 25.05))   # completes calibration
    assert node._calibrated is True
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
    node = VolatilityAux('StdDev', 'sensor', scale=50, auto_scale=True)
    assert node.scale == 50


def test_live_reenable_of_auto_scale_clears_stale_scale():
    # simulates what apply_config_diff's update path does to an existing
    # live node: setattr(node, 'auto_scale', True) - not a fresh __init__
    node = VolatilityAux('StdDev', 'sensor', samples=3, scale=99, auto_scale=False)
    _feed(node, [24.9, 25.0, 25.1])   # some stale state accumulated
    assert node.scale == 99   # untouched while auto_scale is off

    node.auto_scale = True   # live re-toggle, via the property setter
    assert node.scale == 1.0
    assert node._calibrated is False
    assert node._calib_samples == []
    assert node._calib_start is not None

    # accumulates normally now, but doesn't complete until the full
    # 24h duration has elapsed
    node.listen(MsgData('sensor', 30.0))
    assert node.scale == 1.0
    assert node._calibrated is False


def test_toggling_auto_scale_off_leaves_the_calibrated_scale_alone():
    node = VolatilityAux('StdDev', 'sensor', samples=3, auto_scale=True)
    _feed(node, [24.9, 25.0, 25.1])
    node._calib_start = time.time() - VolatilityAux._AUTO_SCALE_DURATION - 1
    node.listen(MsgData('sensor', 25.05))   # completes calibration
    calibrated_scale = node.scale

    node.auto_scale = False
    assert node.scale == calibrated_scale


def test_auto_scale_retries_when_the_accumulated_window_is_perfectly_flat():
    node = VolatilityAux('StdDev', 'sensor', samples=3, auto_scale=True)

    _feed(node, [25.0, 25.0, 25.0, 25.0])   # two flat windows, raw stddev 0.0 each
    node._calib_start = time.time() - VolatilityAux._AUTO_SCALE_DURATION - 1
    node.listen(MsgData('sensor', 25.0))   # duration elapsed, but p90 is still 0.0
    assert node.scale == 1.0
    assert node._calibrated is False
    assert node._calib_samples   # not cleared - still waiting for real variance

    node.listen(MsgData('sensor', 26.0))   # now real variance appears
    assert node.scale != 1.0
    assert node._calibrated is True


def test_auto_scale_off_leaves_scale_at_whatever_was_set():
    node = VolatilityAux('StdDev', 'sensor', samples=3, scale=42, auto_scale=False)
    _feed(node, [24.9, 25.0, 25.1])
    assert node.scale == 42


def test_state_round_trip_preserves_auto_scale():
    node = VolatilityAux('StdDev', 'sensor', auto_scale=True)
    state = node.__getstate__()
    assert state['auto_scale'] is True

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored.auto_scale is True


def test_state_round_trip_defaults_auto_scale_for_pre_existing_saved_nodes():
    # a node saved before 'auto_scale' existed has no such key in its state
    node = VolatilityAux('StdDev', 'sensor')
    state = node.__getstate__()
    del state['auto_scale']

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored.auto_scale is False


def test_state_round_trip_preserves_in_progress_calibration():
    # an ordinary service restart mid-calibration must resume, not
    # restart the 24h clock - otherwise a restart during normal
    # operation (a deploy, an update) could keep a calibration from
    # ever completing
    node = VolatilityAux('StdDev', 'sensor', samples=3, auto_scale=True)
    _feed(node, [24.9, 25.0, 25.1, 24.8])   # accumulating, not yet calibrated
    assert node._calibrated is False
    state = node.__getstate__()

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored._calibrated is False
    assert restored._calib_start == node._calib_start
    assert restored._calib_samples == node._calib_samples
    assert restored.scale == 1.0

    restored._calib_start = time.time() - VolatilityAux._AUTO_SCALE_DURATION - 1
    # _values (the raw reading window) isn't persisted (pre-existing,
    # unrelated behavior - see the samples setter's docstring) so it
    # takes a full refill before a new raw stddev can be computed at all
    _feed(restored, [25.1, 25.0, 25.2])
    assert restored._calibrated is True


def test_state_round_trip_preserves_completed_calibration():
    # this is the actual bug being fixed: the old single-instant design
    # deliberately did NOT persist _calibrated, treating every process
    # restart as a legitimate re-arm (cheap when calibration was one
    # reading). Now that calibration can take up to 24h, a restart
    # discarding a completed one and starting over would be far worse -
    # it must survive an ordinary restart intact.
    node = VolatilityAux('StdDev', 'sensor', samples=3, auto_scale=True)
    _feed(node, [24.9, 25.0, 25.1])
    node._calib_start = time.time() - VolatilityAux._AUTO_SCALE_DURATION - 1
    node.listen(MsgData('sensor', 25.05))
    assert node._calibrated is True
    calibrated_scale = node.scale
    state = node.__getstate__()

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored._calibrated is True
    assert restored.scale == calibrated_scale

    _feed(restored, [10.0, 40.0, 10.0])
    assert restored.scale == calibrated_scale


def test_state_round_trip_defaults_calibration_bookkeeping_for_pre_existing_saved_nodes():
    # a node saved before 'calibrated'/'calib_start'/'calib_samples'
    # existed has none of those keys
    node = VolatilityAux('StdDev', 'sensor', auto_scale=True)
    state = node.__getstate__()
    del state['calibrated']
    del state['calib_start']
    del state['calib_samples']

    restored = VolatilityAux.__new__(VolatilityAux)
    restored.__setstate__(state)
    assert restored._calibrated is False
    assert restored._calib_samples == []
    # _calib_start lazily (re)starts on the next reading rather than
    # staying None forever - equivalent to treating the upgrade as a
    # fresh arm
    assert restored._calib_start is None

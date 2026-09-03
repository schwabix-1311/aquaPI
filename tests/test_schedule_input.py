#!/usr/bin/env python3
""" Tests for ScheduleInput's elapsed-time scheduling math - exercises
    the pure _phase()/_is_on()/_seconds_to_next_wake() methods directly
    with fixed datetimes, no thread/sleep involved.

    All test datetimes are built via a naive datetime + a bare, no-args
    .astimezone() call (see `_local()` below), matching exactly how the
    real code builds `now` (datetime.now().astimezone()) and how
    ScheduleInput._reference()/_seconds_to_next_local_midnight() resolve
    local time - never via an arbitrary fixed-offset timezone(), which
    would silently disagree with whatever the actual system timezone
    resolves "today" to (hit this directly while writing these tests: a
    fixed +1h offset for a June date under Europe/Berlin - a real
    +2h/CEST date - produced numbers that didn't match hand-computed
    expectations at all).
"""
from datetime import datetime, timedelta

import pytest

from aquaPi.machineroom.in_nodes import ScheduleInput


def _local(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi).astimezone()


def test_daily_window():
    node = ScheduleInput('Zeitplan Licht', 24 * 3600, 8 * 3600, anchor='14:00')
    assert node._is_on(_local(2026, 6, 1, 14, 0)) is True
    assert node._is_on(_local(2026, 6, 1, 21, 59)) is True
    assert node._is_on(_local(2026, 6, 1, 22, 0)) is False
    assert node._is_on(_local(2026, 6, 1, 13, 59)) is False
    # same window, winter - the whole point of the wall-clock design is
    # that this doesn't depend on which DST regime "now" falls into
    assert node._is_on(_local(2026, 1, 15, 14, 0)) is True
    assert node._is_on(_local(2026, 1, 15, 22, 0)) is False


def test_degenerate_always_on():
    node = ScheduleInput('Always', 10, 999999)
    assert node._is_on(_local(2026, 1, 1, 0, 0)) is True
    assert node._is_on(_local(2026, 6, 15, 12, 34)) is True


def test_weekday_gate():
    # 2026-06-01 is a Monday; datetime.weekday(): Monday=0 .. Sunday=6
    node = ScheduleInput('Weekdays only', 24 * 3600, 8 * 3600,
                         anchor='14:00', weekdays=[0, 1, 2, 3, 4])
    monday, saturday = _local(2026, 6, 1, 15, 0), _local(2026, 6, 6, 15, 0)
    assert monday.weekday() == 0 and saturday.weekday() == 5
    assert node._is_on(monday) is True
    assert node._is_on(saturday) is False


def test_min_frequency_enforced():
    node = ScheduleInput('Too fast', 0.1, 0.05)
    assert node.frequency == ScheduleInput.MIN_FREQUENCY == 1.0


def test_invalid_anchor_rejected():
    with pytest.raises(ValueError):
        ScheduleInput('Bad', 3600, 60, anchor='25:00')
    with pytest.raises(ValueError):
        ScheduleInput('Bad', 3600, 60, anchor='not-a-time')


def test_invalid_weekday_rejected():
    with pytest.raises(ValueError):
        ScheduleInput('Bad', 3600, 60, weekdays=[7])


def test_seconds_to_next_wake_natural_transition():
    node = ScheduleInput('Zeitplan Licht', 24 * 3600, 8 * 3600, anchor='14:00')
    now = _local(2026, 6, 1, 15, 0)  # 1h into the On window, Off at 22:00
    assert node._seconds_to_next_wake(now) == pytest.approx(7 * 3600)


def test_seconds_to_next_wake_prefers_midnight_when_weekday_gated():
    # Off portion (22:00-14:00 daily); at 23:00 the natural next-On
    # transition is 15h away (14:00 the next day), but midnight is only
    # 1h away - the weekday gate must be re-checked there regardless.
    node = ScheduleInput('Weekdays only', 24 * 3600, 8 * 3600, anchor='14:00', weekdays=[0])
    now = _local(2026, 6, 1, 23, 0)  # Monday
    assert now.weekday() == 0
    wake = node._seconds_to_next_wake(now)
    assert wake == pytest.approx(1 * 3600)
    assert wake < 15 * 3600  # confirms midnight, not the natural transition, won


def test_restart_continuity():
    """ the whole point of the elapsed-time design: the on/off state
        never depends on when the node was created or last restarted,
        only on `now`'s own wall-clock reading - so evaluating "now" at
        two wildly different real times (as if one were freshly
        restarted after years of downtime) agrees exactly.
    """
    node = ScheduleInput('Zeitplan Licht', 24 * 3600, 8 * 3600, anchor='14:00')
    soon = _local(2026, 9, 4, 15, 0)
    much_later = _local(2030, 1, 1, 15, 0)
    assert node._is_on(soon) == node._is_on(much_later) is True


def test_dst_spring_forward_keeps_local_anchor():
    """ anchor stays pinned to the same local wall-clock time even on
        the day the clocks jump forward (2026-03-29 in Europe/Berlin) -
        exercised with real system-local dates, not an injected zone,
        since ScheduleInput's own design deliberately never touches
        tzinfo/DST machinery at all (see _reference()'s docstring) -
        wall-clock arithmetic is DST-oblivious by construction, which is
        exactly what keeps this correct.
    """
    node = ScheduleInput('Zeitplan Licht', 24 * 3600, 8 * 3600, anchor='14:00')
    before = _local(2026, 3, 29, 13, 0)   # transition day, before 14:00
    after = _local(2026, 3, 29, 15, 0)    # same day, after 14:00
    next_day = _local(2026, 3, 30, 14, 0)
    assert node._is_on(before) is False
    assert node._is_on(after) is True
    assert node._is_on(next_day) is True


def test_real_world_examples():
    """ the three concrete use cases given directly by the user, none
        of which a cron-based schedule could express without drift. """
    doser = ScheduleInput('Doser', 3 * 86400, 13)  # every 3 days, for 13s
    assert doser.frequency == 3 * 86400 and doser.duration == 13

    filter_reminder = ScheduleInput('Filter reminder', 14 * 86400, 60)  # every 2 weeks
    assert filter_reminder.frequency == 14 * 86400

    pulse = ScheduleInput('Pulse', 5, 1)  # a plain pulse every 5s
    assert pulse.frequency == 5 and pulse.duration == 1
    on_times = [t for t in range(0, 20) if pulse._is_on(_local(2026, 1, 1, 0, 0) + timedelta(seconds=t))]
    assert on_times == [0, 5, 10, 15]

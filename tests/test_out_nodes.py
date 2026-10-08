#!/usr/bin/env python3
""" Tests for machineroom/out_nodes.py: SlowPwmDevice's fixed cycle grid -
    new input values must not restart the PWM cycle (which used to bias the
    output towards 100% whenever values arrived faster than the cycle).
    These run the real pulse thread against a recording fake driver with a
    sub-second cycle, so tolerances are generous.
"""

# pylint: disable=protected-access
import threading
import time

import pytest

from aquaPi.machineroom.out_nodes import SlowPwmDevice


class _RecordingDriver:
    def __init__(self):
        self.writes = []    # [(monotonic time, state), ...]
        self._lock = threading.Lock()

    def write(self, state):
        with self._lock:
            self.writes.append((time.monotonic(), bool(state)))

    def on_fraction(self, start: float, end: float) -> float:
        """ share of [start, end] the output was on """
        with self._lock:
            writes = list(self.writes)
        on_time, state, t_prev = 0.0, False, start
        for t, s in writes:
            if t <= start:
                state = s
                continue
            if t >= end:
                break
            if state:
                on_time += t - t_prev
            state, t_prev = s, t
        if state:
            on_time += end - t_prev
        return on_time / (end - start)

    def state(self) -> bool:
        with self._lock:
            return self.writes[-1][1] if self.writes else False


def _pullout(node):
    # the fake driver isn't registered for a port, so detach it before
    # pullout() releases the (empty) port's driver
    driver, node._driver = node._driver, None
    node.pullout()
    return driver


@pytest.fixture
def pwm():
    node = SlowPwmDevice('Heizstab', 'pid', '', cycle=1.0)
    node._driver = _RecordingDriver()
    # the pulse thread was already running before the driver got attached
    node._driver.writes.append((time.monotonic(), node._on))
    yield node
    if node._driver:
        _pullout(node)


def test_values_faster_than_the_cycle_keep_their_duty(pwm):
    # the old restart-on-every-value behaviour turned this 30% into ~100%:
    # every new value restarted the cycle with its on-phase first
    pwm.set(30.0)
    start = time.monotonic()
    while time.monotonic() - start < 4.0:
        time.sleep(0.25)
        pwm.set(30.0)
    assert pwm._driver.on_fraction(start, start + 4.0) == pytest.approx(0.30, abs=0.08)


def test_steady_value_gives_its_duty(pwm):
    pwm.set(70.0)
    start = time.monotonic()
    time.sleep(3.0)
    assert pwm._driver.on_fraction(start, start + 3.0) == pytest.approx(0.70, abs=0.08)


def test_switch_off_does_not_wait_for_the_cycle(pwm):
    pwm.cycle = 5.0            # takes effect at the next cycle boundary (<= 1s)
    pwm.set(100.0)
    time.sleep(1.2)            # ... which then starts fully on
    assert pwm._driver.state() is True
    pwm.set(0.0)
    time.sleep(0.3)
    assert pwm._driver.state() is False


def test_pullout_stops_the_pulse_thread(pwm):
    thread = pwm._thread
    _pullout(pwm)
    thread.join(timeout=2.0)
    assert not thread.is_alive()

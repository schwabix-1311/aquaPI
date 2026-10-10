#!/usr/bin/env python3
""" Tests for DriverADS1115's auto-range (aquaPi/driver/DriverADC.py), with a
    fake chip: no I²C, no hardware.
"""

import threading

import pytest

import aquaPi.driver.DriverADC as adc


class _FakeAds:
    gains = (2 / 3, 1, 2, 4, 8, 16)

    def __init__(self):
        self.gain = 1


class _FakeIn:
    """ raw counts as the real chip reports them for a fixed input voltage """
    def __init__(self, ads, volts):
        self._ads = ads
        self.volts = volts

    @property
    def value(self):
        full_scale = 6.144 if self._ads.gain < 1 else 4.096 / self._ads.gain
        return int(max(-32768, min(32767, self.volts / full_scale * 32768)))


def _driver(volts):
    drv = adc.DriverADS1115.__new__(adc.DriverADS1115)
    drv._ads = _FakeAds()
    drv._ana_in = _FakeIn(drv._ads, volts)
    drv.gain = -1   # auto-gain, starting at gain 1
    drv._closed = True  # built without __init__: nothing for __del__ to close
    return drv


def _adjust(drv):
    # run in a thread: before the fix, small inputs looped forever
    t = threading.Thread(target=drv._adjust_gain, daemon=True)
    t.start()
    t.join(2)
    assert not t.is_alive(), '_adjust_gain() did not return'


@pytest.mark.parametrize('volts, gain', [(1.65, 2), (0.3, 8), (0.2, 16)])
def test_auto_gain_picks_the_smallest_fitting_range(volts, gain):
    drv = _driver(volts)
    _adjust(drv)
    assert drv._ads.gain == gain
    assert drv.gain == -gain    # remembered as auto-gain


@pytest.mark.parametrize('volts', [0.05, 0.0, -0.05])
def test_auto_gain_near_zero_stops_at_the_smallest_range(volts):
    drv = _driver(volts)
    _adjust(drv)
    assert drv._ads.gain == 16


def test_auto_gain_negative_input_ranges_like_positive():
    # a differential read can be negative - the range follows its magnitude
    drv = _driver(-0.3)
    _adjust(drv)
    assert drv._ads.gain == 8


def test_auto_gain_overrange_stops_at_the_largest_range():
    drv = _driver(7.0)
    drv._ads.gain = 16
    _adjust(drv)
    assert drv._ads.gain == 2 / 3

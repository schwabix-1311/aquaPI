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


class _FakeI2CDevice:
    """ register file of a chip at one I²C address, 16 bit per register """
    device_address = 0x48

    def __init__(self, regs):
        self.regs = regs

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def write_then_readinto(self, out_buf, in_buf, in_start=0, in_end=None):
        in_buf[in_start:in_end] = self.regs[out_buf[0]].to_bytes(2, 'big')


class _FakeDetectAds:
    def __init__(self, config, lo=0x8000, hi=0x7FFF):
        self.i2c_device = _FakeI2CDevice({0: 0, 1: config, 2: lo, 3: hi})


@pytest.mark.parametrize('config', [
    0x8583,     # power-on default, or after a clean _do_close()
    0xC983,     # left behind by an unclean exit: single-ended AIN0, gain 4
    0x4D83,     # same, caught mid-conversion (OS=0), gain 16
    0xF383,     # unclean exit after reading AIN3 single-ended, gain 1
])
def test_is_ads111x_detects_chip(config):
    assert adc.DriverADS1115.is_ads111x(_FakeDetectAds(config))


@pytest.mark.parametrize('ads', [
    _FakeDetectAds(0x8483),                 # continuous mode: someone else uses it
    _FakeDetectAds(0x9583),                 # differential AIN0-3, aquaPi never reads that
    _FakeDetectAds(0xB583),                 # differential AIN2-3
    _FakeDetectAds(0x8503),                 # low config byte differs
    _FakeDetectAds(0x8583, lo=0x1234),      # thresholds changed: another device
    _FakeDetectAds(0x8583, hi=0x0000),
])
def test_is_ads111x_rejects_other_devices(ads):
    assert not adc.DriverADS1115.is_ads111x(ads)

#!/usr/bin/env python3
""" Tests for DriverPCA9685 (aquaPi/driver/DriverPCA9685.py) against a fake
    chip that only records register traffic: no I²C, no hardware.
"""

import pytest

import aquaPi.driver.base as base
import aquaPi.driver.DriverPCA9685 as pca
from aquaPi.driver import PortFunc


class _FakeDev:
    """ register file of a PCA9685, power-on values by default """

    def __init__(self, mode1=0x11, mode2=0x04, prescale=0x1E):
        self.regs = bytearray(256)
        self.regs[pca.MODE1] = mode1
        self.regs[pca.MODE2] = mode2
        self.regs[pca.PRESCALE] = prescale
        for ch in range(16):            # LEDn_OFF_H: full off at power-on
            self.regs[pca.LED0_ON_L + 4 * ch + 3] = 0x10
        self.writes = []

    def write(self, buf):
        self.writes.append(bytes(buf))
        for i, val in enumerate(buf[1:]):
            self.regs[buf[0] + i] = val
        # the chip clears RESTART once it resumed
        self.regs[pca.MODE1] &= 0x7F

    def write_then_readinto(self, out, inbuf):
        inbuf[0] = self.regs[out[0]]

    def led(self, ch):
        r = pca.LED0_ON_L + 4 * ch
        return (self.regs[r] | self.regs[r + 1] << 8,
                self.regs[r + 2] | self.regs[r + 3] << 8)


@pytest.mark.parametrize('percent, regs', [
    (0, (0, 0x1000)),           # full off, no residual pulse
    (-5, (0, 0x1000)),
    (0.001, (0, 0x1000)),       # rounds to 0 counts
    (50, (0, 2048)),
    (1, (0, 41)),
    (100, (0x1000, 0)),         # full on
    (99.99, (0x1000, 0)),
])
def test_duty_to_regs(percent, regs):
    assert pca.duty_to_regs(percent) == regs


def test_prescale_for():
    assert pca.prescale_for(1500) == 3      # the chip's minimum, ~1526 Hz
    assert pca.prescale_for(200) == 30
    assert pca.prescale_for(1) == 255


def test_setup_from_power_on_sets_prescale_and_wakes():
    dev = _FakeDev()
    pca._Chip(dev, 1500)
    assert dev.regs[pca.PRESCALE] == 3
    assert dev.regs[pca.MODE1] & pca.SLEEP == 0
    assert dev.regs[pca.MODE1] & pca.AI


def test_setup_on_a_running_chip_writes_nothing():
    # aquaPi restart without power loss: other channels must keep running
    dev = _FakeDev(mode1=0x21, prescale=3)
    pca._Chip(dev, 1500)
    assert dev.writes == []


def test_setup_frequency_change_sleeps_first_then_restarts():
    dev = _FakeDev(mode1=0x21, prescale=30)
    pca._Chip(dev, 1500)
    assert dev.writes[0] == bytes([pca.MODE1, 0x21 | pca.SLEEP])
    assert dev.writes[1] == bytes([pca.PRESCALE, 3])
    assert dev.regs[pca.MODE1] & pca.SLEEP == 0


@pytest.mark.parametrize('dev, ok', [
    (_FakeDev(), True),                             # power-on values
    (_FakeDev(mode1=0x21, prescale=3), True),       # after running
    (_FakeDev(mode2=0xFF), False),                  # reserved bits set
    (_FakeDev(prescale=0), False),
])
def test_is_pca9685(dev, ok):
    assert pca.is_pca9685(dev) is ok


def test_is_pca9685_survives_a_bus_error():
    class _Broken:
        def write_then_readinto(self, out, inbuf):
            raise OSError('Remote I/O error')
    assert pca.is_pca9685(_Broken()) is False


@pytest.fixture
def chip_dev(monkeypatch):
    """ make the driver believe it runs on a Pi, with fake chips """
    devs = {}

    def _open(adr):
        devs[adr] = _FakeDev()
        return devs[adr]

    monkeypatch.setattr(base, 'is_raspi', lambda: True)
    monkeypatch.setattr(pca, '_open_device', _open)
    monkeypatch.setattr(pca, '_chips', {})
    return devs


def _drv(func, ch=0, adr=0x40):
    return pca.DriverPCA9685({'adr': adr, 'cnt': 1, 'ch': ch}, func)


def test_dimmer_channel(chip_dev):
    drv = _drv(PortFunc.Aout, ch=3)
    dev = chip_dev[0x40]
    drv.write(25)
    assert dev.led(3) == (0, 1024)
    drv.write(100)
    assert dev.led(3) == (0x1000, 0)
    assert drv.read() == 100.0
    drv.close()
    assert dev.led(3) == (0, 0x1000)


@pytest.mark.parametrize('on', [True, 100, 1])
def test_binary_channel(chip_dev, on):
    # SwitchDevice writes 100/0, SlowPwmDevice True/False
    drv = _drv(PortFunc.Bout, ch=15)
    dev = chip_dev[0x40]
    drv.write(on)
    assert dev.led(15) == (0x1000, 0)
    assert drv.read() is True
    drv.write(0)
    assert dev.led(15) == (0, 0x1000)
    drv.close()


def test_channels_share_one_chip(chip_dev):
    a = _drv(PortFunc.Aout, ch=0)
    b = _drv(PortFunc.Bout, ch=1)
    assert a._chip is b._chip
    assert pca._chips[0x40].users == 2
    a.close()
    assert pca._chips[0x40].users == 1
    b.close()
    assert 0x40 not in pca._chips


def test_new_channel_starts_off(chip_dev):
    _drv(PortFunc.Aout, ch=2)
    assert chip_dev[0x40].led(2) == (0, 0x1000)


def test_simulated_ports():
    ports = pca.DriverPCA9685.find_ports()       # dev machine: simulated
    assert len(ports) == 32
    pwm, out = ports['PCA9685 #1 CH7 PWM'], ports['PCA9685 #1 CH7 out']
    assert pwm.func == PortFunc.Aout and out.func == PortFunc.Bout
    assert 'PCA9685 #1 CH7 PWM' in out.deps
    drv = pwm.driver(pwm.cfg, pwm.func)
    drv.write(40)
    assert drv.read() == 40.0
    assert drv.name.startswith('!')


def test_port_lists_sort_numerically():
    from aquaPi.driver import natural_key
    from aquaPi.driver import create_io_registry
    from aquaPi.machineroom.out_nodes import AnalogDevice

    assert sorted(['CH10', 'CH2', 'GPIO 12 out', 'GPIO 2 out'], key=natural_key) \
        == ['CH2', 'CH10', 'GPIO 2 out', 'GPIO 12 out']
    create_io_registry()
    opts = [p for p in AnalogDevice.get_port_schema('port').options if p.startswith('PCA9685')]
    assert opts[:3] == ['PCA9685 #1 CH0 PWM', 'PCA9685 #1 CH1 PWM', 'PCA9685 #1 CH2 PWM']
    assert opts[-1] == 'PCA9685 #1 CH15 PWM'

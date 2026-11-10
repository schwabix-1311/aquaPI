#!/usr/bin/env python3
""" NXP PCA9685: 16 channel, 12 bit PWM controller on I²C.

    Every channel is offered twice - as a dimmer ('PCA9685 #1 CH0 PWM',
    Aout) and as an on/off output ('PCA9685 #1 CH0 out', Bout). The Bout
    port depends on its Aout port, so the IoRegistry refuses the second
    claim of a channel in either order, the same way 'PWM 0' and
    'GPIO 18 out' exclude each other.

    All channels of a chip share one prescaler, i.e. one PWM frequency.
"""

import logging
import threading
import time

import board  # type: ignore[import-untyped]
import busio  # type: ignore[import-untyped]
from adafruit_bus_device.i2c_device import I2CDevice  # type: ignore[import-untyped]

from .base import (OutDriver, IoPort, PortFunc, is_raspi)


log = logging.getLogger('driver.DriverPCA9685')


# ========== registers ==========

MODE1 = 0x00
MODE2 = 0x01
LED0_ON_L = 0x06
PRESCALE = 0xFE

RESTART = 0x80
AI = 0x20           # register auto-increment
SLEEP = 0x10
FULL = 0x1000       # bit 4 of LEDn_ON_H / LEDn_OFF_H: full on / full off

OSC_HZ = 25_000_000
DEFAULT_FREQ = 1500     # Hz, as aquaPCB, Robo-Tank and reef-pi assume


def prescale_for(freq: float) -> int:
    """ PRESCALE register value for a PWM frequency, datasheet 7.3.5 """
    return min(255, max(3, round(OSC_HZ / (4096 * freq)) - 1))


def duty_to_regs(percent: float) -> tuple[int, int]:
    """ (ON, OFF) counts for a duty cycle in %, using the full on/off bits
        at the ends so 0 % and 100 % have no residual pulse
    """
    off = round(percent * 40.95)
    if off <= 0:
        return 0, FULL
    if off >= 4095:
        return FULL, 0
    return 0, off


def _read_reg(dev, reg: int) -> int:
    buf = bytearray(1)
    dev.write_then_readinto(bytes([reg]), buf)
    return buf[0]


def is_pca9685(dev) -> bool:
    """ read-only plausibility check: reserved bits read as 0, and the
        chip never reports a prescaler below 3
    """
    try:
        if _read_reg(dev, MODE2) & 0xE0:
            return False
        if _read_reg(dev, PRESCALE) < 3:
            return False
        for reg in (LED0_ON_L + 1, LED0_ON_L + 3):     # LED0_ON_H, LED0_OFF_H
            if _read_reg(dev, reg) & 0xE0:
                return False
        return True
    except Exception as ex:
        log.debug('I²C device check failed: %r', ex)
        return False


# ========== one shared object per chip ==========


class _Chip:
    """ the chip behind up to 16 channel drivers: one lock for the I²C
        traffic and a count of the drivers using it
    """

    def __init__(self, dev, freq: float = DEFAULT_FREQ):
        self.dev = dev
        self.lock = threading.Lock()
        self.users = 0
        self._setup(freq)

    def _setup(self, freq: float) -> None:
        """ set frequency and auto-increment. Sleeps the chip (stopping all
            its channels) only if the prescaler really has to change - an
            aquaPi restart without power loss leaves the others running.
            No software reset: other channels may be in use.
        """
        prescale = prescale_for(freq)
        with self.lock:
            mode1 = _read_reg(self.dev, MODE1)
            if _read_reg(self.dev, PRESCALE) != prescale:
                self.dev.write(bytes([MODE1, (mode1 & ~RESTART & 0xFF) | SLEEP]))
                self.dev.write(bytes([PRESCALE, prescale]))
                mode1 = _read_reg(self.dev, MODE1)
            if mode1 & SLEEP or not mode1 & AI:
                # writing 0 to RESTART has no effect, 1 resumes the PWM
                awake = (mode1 & ~(RESTART | SLEEP) & 0xFF) | AI
                self.dev.write(bytes([MODE1, awake]))
                time.sleep(0.0005)      # oscillator start-up
                if mode1 & RESTART:
                    self.dev.write(bytes([MODE1, awake | RESTART]))

    def set_duty(self, ch: int, percent: float) -> None:
        on, off = duty_to_regs(percent)
        with self.lock:
            self.dev.write(bytes([LED0_ON_L + 4 * ch,
                                  on & 0xFF, on >> 8, off & 0xFF, off >> 8]))


_chips: dict[int, _Chip] = {}
_chips_lock = threading.Lock()


def _open_device(adr: int):
    return I2CDevice(busio.I2C(board.SCL, board.SDA), adr)


def _acquire(adr: int, freq: float) -> _Chip:
    with _chips_lock:
        chip = _chips.get(adr)
        if chip is None:
            chip = _chips[adr] = _Chip(_open_device(adr), freq)
        chip.users += 1
        return chip


def _release(adr: int) -> None:
    with _chips_lock:
        chip = _chips.get(adr)
        if chip is not None:
            chip.users -= 1
            if chip.users <= 0:
                del _chips[adr]


# ========== driver ==========


def _chip_ports(cnt: int, cfg: dict, bus_deps: list[str]) -> dict[str, IoPort]:
    ports = {}
    for ch in range(16):
        pwm_name = f'PCA9685 #{cnt} CH{ch} PWM'
        ch_cfg = dict(cfg, cnt=cnt, ch=ch)
        ports[pwm_name] = IoPort(PortFunc.Aout, DriverPCA9685, ch_cfg, list(bus_deps))
        ports[f'PCA9685 #{cnt} CH{ch} out'] = IoPort(PortFunc.Bout, DriverPCA9685,
                                                     dict(ch_cfg), [pwm_name] + bus_deps)
    return ports


class DriverPCA9685(OutDriver):
    """ one channel of a PCA9685, either as dimmer (Aout, 0..100 %) or
        as on/off output (Bout)
    """

    # 0x40..0x47 = address jumpers A0..A2; above are the ADS1115
    # (0x48..0x4B) and the PCA9685 All-Call address 0x70
    ADDRESSES = range(0x40, 0x48)
    _BUS = 'I2C'

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        if not is_raspi():
            log.info('Faking I²C - PCA9685 ...')
            return _chip_ports(1, {'adr': 0x40, 'fake': True}, ['GPIO 2 in', 'GPIO 2 out'])

        log.info('Scanning I²C bus for PCA9685 ...')
        bus_deps = ['GPIO %d in' % board.SCL.id, 'GPIO %d out' % board.SCL.id,
                    'GPIO %d in' % board.SDA.id, 'GPIO %d out' % board.SDA.id]
        i2c = busio.I2C(board.SCL, board.SDA)
        ports: dict[str, IoPort] = {}
        cnt = 0
        for adr in DriverPCA9685.ADDRESSES:
            try:
                dev = I2CDevice(i2c, adr)
            except ValueError:
                continue        # nothing answers at this address
            if is_pca9685(dev):
                cnt += 1
                ports.update(_chip_ports(cnt, {'adr': adr}, bus_deps))
                log.info('PCA9685 #%d at 0x%02X', cnt, adr)
            else:
                log.info('I²C device at 0x%02X is not a PCA9685', adr)
        return ports

    def __init__(self, cfg: dict, func: PortFunc):
        super().__init__(cfg, func)
        self._adr = int(cfg['adr'])
        self._ch = int(cfg['ch'])
        kind = 'out' if self._is_binary() else 'PWM'
        self.name = self._mark_fake(f"PCA9685 #{cfg['cnt']} CH{self._ch} {kind}")
        self._chip: _Chip | None = None
        if not self._fake:
            self._chip = _acquire(self._adr, float(cfg.get('freq', DEFAULT_FREQ)))
        self.write(0)

    def _is_binary(self) -> bool:
        return self.func == PortFunc.Bout

    def write(self, value) -> None:
        if self._is_binary():
            self._val = bool(value)
            percent = 100. if self._val else 0.
        else:
            self._val = percent = min(max(float(value), 0.), 100.)
        log.verbose('%s -> %r', self.name, self._val)
        if self._chip:
            self._chip.set_duty(self._ch, percent)

    def _do_close(self) -> None:
        if self._chip:
            try:
                self._chip.set_duty(self._ch, 0)
            finally:
                self._chip = None
                _release(self._adr)

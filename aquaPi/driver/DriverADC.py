#!/usr/bin/env python3

import logging
import statistics

# latest Blinka supports x86 LinuxPC, but we don't at least not chips on I²C
from adafruit_platformdetect import Detector  # type: ignore[import-untyped]
SIMULATED: bool = Detector().board.id == 'GENERIC_LINUX_PC'

import board  # type: ignore[import-untyped]
import busio  # type: ignore[import-untyped]

# from adafruit_ads1x15 import ADS1015
from adafruit_ads1x15.ads1115 import ADS1115
from adafruit_ads1x15.analog_in import AnalogIn

from .base import (AInDriver, IoPort, PortFunc, gpio_deps)


log = logging.getLogger('driver.DriverADC')


# ========== ADC inputs ==========


adc_count: int = 0


class DriverADS1115(AInDriver):
    """ A driver for TI's 16bit ADC ADS1113/4/5, and 12bit ADS1013/4/5
        Chip variants:
            ADS1x13 1 channel, no comparator
            ADS1x14 1 channel, gain adjustable
            ADS1x15 4 channel or 2 differential, gain adjustable
        Sample rate and continuous mode not supported. Differential isn't yet.
    """

    ADDRESSES = [0x48, 0x49, 0x4A, 0x4B]
    _BUS = 'I2C'

    @staticmethod
    def is_ads111x(ads: ADS1115) -> bool:
        """ check power-on register defaults of ADS1113/4/5
        """
        try:
            buf = bytearray(8)
            with ads.i2c_device as device:
                device.write_then_readinto(
                    bytearray([0]), buf, in_start=0, in_end=2)
                device.write_then_readinto(
                    bytearray([1]), buf, in_start=2, in_end=4)
                device.write_then_readinto(
                    bytearray([2]), buf, in_start=4, in_end=6)
                device.write_then_readinto(
                    bytearray([3]), buf, in_start=6, in_end=8)
                # power-on default is config 0x8583 (OS idle, MUX AIN0-1,
                # PGA ±2.048V, single-shot, 128SPS, comparator off) and
                # thresholds 0x8000/0x7FFF. _do_close() restores that, but
                # an unclean exit leaves aquaPi's last read config, which
                # (Pi reboots don't power-cycle the chip) must not lose the
                # ADC: so accept any OS and PGA, plus single-ended MUX
                # (1xx). Anything aquaPi never writes - differential MUX
                # 001..011, continuous mode, other data rate/comparator,
                # changed thresholds - means another program is using the
                # chip: reject it.
                mux = (buf[2] >> 4) & 0x07
                if (mux in (0, 4, 5, 6, 7) and buf[2] & 0x01
                        and buf[3:8] == bytearray.fromhex('83 8000 7FFF')):
                    return True
                log.debug('I²C device @ 0x%02X returns 0x%s 0x%s 0x%s' +
                          ' from reg 1..3, probably a different device,' +
                          ' or already in use.',
                          device.device_address,
                          bytes(buf[2:4]).hex(),
                          bytes(buf[4:6]).hex(),
                          bytes(buf[6:8]).hex())
        except Exception as ex:
            log.debug('Exception %r', ex)
        return False

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        global adc_count  # pylint: disable=W0603

        if SIMULATED:
            return DriverADS1115._simulated_ports()

        i2c = busio.I2C(board.SCL, board.SDA)
        deps = gpio_deps(board.SCL.id, board.SDA.id)
        ports = {}

        log.info('Scanning I²C bus for ADS1x13/4/5 ...')
        # autodetect of I²C is undefined and risky, as some chips may react on
        # read as if it was a write! We're on a pretty well defined HW though.
        for adr in DriverADS1115.ADDRESSES:
            try:
                ads = ADS1115(i2c, address=adr)
            except Exception:
                continue        # nothing answers at this address
            if DriverADS1115.is_ads111x(ads):
                adc_count += 1
                for ch in range(4):
                    ports[f'ADC #{adc_count} in {ch}'] = IoPort(
                        PortFunc.Ain, DriverADS1115,
                        {'adr': adr, 'cnt': adc_count, 'in': ch}, deps)
            else:
                log.info('I²C device at 0x%02X seems not to be an ADS1x15, '
                         'probably a different device, or already in use.', adr)
        return ports

    @staticmethod
    def _simulated_ports() -> dict[str, IoPort]:
        global adc_count  # pylint: disable=W0603

        log.info('Faking I²C - ADS1x13/4/5 ...')
        adc_count += 1
        return {
            f'ADC #{adc_count} in {ch}':
            IoPort(PortFunc.Ain, AInDriver,
                   {'cnt': adc_count, 'in': ch, 'fake': True}, gpio_deps(2))
            for ch in range(4)
        }

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        cnt = int(cfg['cnt'])
        adr = int(cfg['adr'])
        inp = int(cfg['in'])
        self.gain: float = float(cfg.get('gain', -16))
        self.name = f'ADC #{cnt} (ADS1115 @0x{adr:02X} in {inp})'

        i2c = busio.I2C(board.SCL, board.SDA)
        self._ads = ADS1115(i2c, address=adr, gain=abs(self.gain))
        self._ana_in: AnalogIn = AnalogIn(self._ads, inp)
        self._median_filter: bool = True  # const ATM

    def _do_close(self) -> None:
        if self._fake:
            return

        # return chip to power-on defaults to allow future auto-detect
        self._ads.gain = 2
        self._ads.read(0)

    def read(self) -> float:
        if self._fake:
            return super().read()

        self._adjust_gain()
        if not self._median_filter:
            self._val = self._ana_in.voltage
        else:
            samples = [self._ana_in.voltage for _ in range(3)]
            log.debug('median of %r', samples)
            self._val = statistics.median(samples)

        log.verbose('%s = %f', self.name, self._val)
        return self._val

    def _increase_gain(self) -> bool:
        """ step to the next larger input range; False if already at the largest """
        ads = self._ads
        lower = [g for g in ads.gains if g < ads.gain]
        if lower:
            ads.gain = lower[-1]
        return bool(lower)

    def _decrease_gain(self) -> bool:
        """ step to the next smaller input range; False if already at the smallest """
        ads = self._ads
        higher = [g for g in ads.gains if g > ads.gain]
        if higher:
            ads.gain = higher[0]
        return bool(higher)

    def _adjust_gain(self) -> None:
        """ gain <= 0 is auto-gain.
            Since there's only a common gain for all channels,
            we need repeated conversions, and increase I2C traffic.
        """
        ads = self._ads
        ads.gain = abs(self.gain)
        if self.gain <= 0:
            val = self._ana_in.value

            # stop at either end of the gain table: a signal below half of
            # the smallest range (< 128 mV) or above the largest one can't
            # be ranged any further - without the check this looped forever
            # and froze the reader thread for any input near 0 V
            while abs(val) > 32300:
                if not self._increase_gain():
                    break
                val = self._ana_in.value

            while abs(val) < 16000:
                if not self._decrease_gain():
                    break
                val = self._ana_in.value

            self.gain = -ads.gain
            log.debug('ADS gain %d (%d), digits %f', ads.gain, self.gain, val)

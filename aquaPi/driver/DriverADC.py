#!/usr/bin/env python3

import logging

# latest Blinka supports x86 LinuxPC, but we don't at least not chips on I²C
from adafruit_platformdetect import Detector  # type: ignore[import-untyped]
if not Detector().board.id == 'GENERIC_LINUX_PC':
    SIMULATED = False
else:
    SIMULATED = True

import board  # type: ignore[import-untyped]
import busio  # type: ignore[import-untyped]
from adafruit_ads1x15.ads1115 import ADS1115, P0, P1, P2, P3
from adafruit_ads1x15.analog_in import AnalogIn


from .base import (AInDriver, IoPort, PortFunc)


log = logging.getLogger('driver.DriverADC')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


# ========== ADC inputs ==========


adc_count: int = 0


class DriverADS1115(AInDriver):
    """ A driver for TI's 16bit ADC ADS1113/4/5, and 12bit ADS1013/4/5
        # back to defaults to enable our auto-datect
        Chip variants:
            ADS1x13 1 channel, no comparator
            ADS1x14 1 channel, gain adjustable
            ADS1x15 4 channel or 2 differential, gain adjustable
        Sample rate and continuous mode not supported. Differential isn't yet.
    """

    ADDRESSES = [0x48, 0x49, 0x4A, 0x4B]
    CHANNELS = [P0, P1, P2, P3]  # ATM no differential channels

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
                # default is: in 0-1 differential, gain 2, 1 shot, 128SPS, comp low, no latch, disable comp
                if buf[2:8] == bytearray.fromhex('8583 8000 7FFF'):
                    return True
                # TODO: DBG REMOVE_ME!
                if buf[3:8] == bytearray.fromhex('83 8000 7FFF'):
                    return True
                log.debug('I²C device @ 0x%02X returns 0x%s 0x%s 0x%s' +
                          ' from reg 1..3, probably a different device,' +
                          ' or already in use.',
                          device.device_address,
                          bytes(buf[2:4]).hex(),
                          bytes(buf[4:6]).hex(),
                          bytes(buf[6:8]).hex())
        except Exception as ex:
            # pass  # whatever it is, ignore device @ this adr!
            log.debug('Exception %r', ex)
        return False

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        global adc_count  # pylint: disable=W0603

        io_ports = {}
        if not SIMULATED:
            # autodetect of I²C is undefined and risky, as some chips may react
            # on read as if it was a write! We're on a pretty well defined HW though.
            i2c = busio.I2C(board.SCL, board.SDA)
            deps = ['GPIO %d in' % board.SCL.id, 'GPIO %d out' % board.SCL.id,
                    'GPIO %d in' % board.SDA.id, 'GPIO %d out' % board.SDA.id]

            # one loop for each chip type
            log.brief('Scanning I²C bus for ADS1x13/4/5 ...')
            for adr in DriverADS1115.ADDRESSES:
                try:
                    ads = ADS1115(i2c, address=adr)
                    if DriverADS1115.is_ads111x(ads):
                        adc_count += 1
                        for ch in DriverADS1115.CHANNELS:
                            port_name = f'ADC #{adc_count} in {ch}'
                            port_cfg = {'adr': adr, 'cnt': adc_count, 'in': ch}
                            io_ports[port_name] = IoPort(PortFunc.Ain,
                                                         DriverADS1115,
                                                         port_cfg,
                                                         deps)
                    else:
                        log.brief('I²C device at 0x%02X seems not to be an '
                                  'ADS1x15, probably a different device, '
                                  'or already in use.', adr)
                except ValueError as ex:
                    log.info(ex)
                except Exception as ex:
                    # pass  # whatever it is, ignore this device
                    log.debug('%r', ex)
        else:  # SIMULATED
            deps = ['GPIO 2 in', 'GPIO 2 out']
            adc_count += 1
            port_name = 'ADC #%d in ' % adc_count
            # name: IoPort(portFunction, drvClass, configDict, dependantsArray)
            io_ports = {
                port_name + '0': IoPort(PortFunc.Ain, AInDriver, {'cnt': adc_count, 'in': 0, 'fake': True}, deps),
                port_name + '1': IoPort(PortFunc.Ain, AInDriver, {'cnt': adc_count, 'in': 1, 'fake': True}, deps),
                port_name + '2': IoPort(PortFunc.Ain, AInDriver, {'cnt': adc_count, 'in': 2, 'fake': True}, deps),
                port_name + '3': IoPort(PortFunc.Ain, AInDriver, {'cnt': adc_count, 'in': 3, 'fake': True}, deps)
            }
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        cnt = int(cfg['cnt'])
        adr = int(cfg['adr'])
        inp = int(cfg['in'])
        self.gain: float = float(cfg.get('gain', -16))
        self.cfg: dict[str, str] = cfg
        self.name: str = f'ADC #{cnt} (ADS1115 @0x{adr:02X} in {inp}'

        i2c = busio.I2C(board.SCL, board.SDA)
        self._ads = ADS1115(i2c, address=adr, gain=abs(self.gain))
        self._ana_in: AnalogIn = AnalogIn(self._ads, inp)
        self._median_filter: bool = True  # const ATM

    def close(self) -> None:
        if self._fake:
            return super().close()

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
            median = [self._ana_in.voltage,
                      self._ana_in.voltage,
                      self._ana_in.voltage]
            median.sort()
            log.debug('median %f %f %f', median[0], median[1], median[2])
            self._val = median[2]

        log.info('%s = %f', self.name, self._val)
        return self._val

    def _adjust_gain(self) -> None:
        """ gain <= 0 is auto-gain.
            Since there's only a common gain for all channels,
            we need repeated conversions, and increase I2C traffic.
        """
        ads = self._ads
        ads.gain = abs(self.gain)
        if self.gain <= 0:
            val = self._ana_in.value
            while abs(val) > 32300:
                l_gain = [ads.gains[0]] + \
                    [g for g in ads.gains if g < ads.gain]
                ads.gain = l_gain[-1]
                val = self._ana_in.value
            while abs(val) < 16000:
                h_gain = [g for g in ads.gains if g <
                          ads.gain] + [ads.gains[-1]]
                ads.gain = h_gain[0]
                val = self._ana_in.value
            self.gain = -ads.gain
            log.debug('ADS gain %d (%d), digits %f', ads.gain, self.gain, val)

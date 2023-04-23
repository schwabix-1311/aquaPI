#!/usr/bin/env python3

from enum import Enum
import logging

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    # import adafruit_ads1x15.ads1015 as ADSxx
    from adafruit_ads1x15.analog_in import AnalogIn

    SIMULATED = False
except NotImplementedError:
    SIMULATED = True

    class ADS(Enum):
        P0, P1, P2, P3 = range(0, 4)

from .base import (AInDriver, IoPort, PortFunc)

log = logging.getLogger('DriverADS111x')
log.brief = log.warning  # alias, warning used as brief info, info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== ADC inputs ==========


adc_count = 0


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
    CHANNELS = [ADS.P0, ADS.P1, ADS.P2, ADS.P3]  # ATM no differential channels

    @staticmethod
    def is_ads111x(ads):
        """ check power-on register defaults of ADS1113/4/5
        """
        try:
            buf = bytearray(8)
            with ads.i2c_device as device:
                device.write_then_readinto(bytearray([0]), buf, in_start=0, in_end=2)
                device.write_then_readinto(bytearray([1]), buf, in_start=2, in_end=4)
                device.write_then_readinto(bytearray([2]), buf, in_start=4, in_end=6)
                device.write_then_readinto(bytearray([3]), buf, in_start=6, in_end=8)
                # default is: in 0-1 differential, gain 2, 1 shot, 128SPS, comp low, no latch, disable comp
                if buf[2:8] == bytearray.fromhex('8583 8000 7FFF'):
                    return True
                if buf[3:8] == bytearray.fromhex('83 8000 7FFF'):   # TODO: DBG REMOVE_ME!
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
            # pass  # whatever it is, ignore device @ this adr!
        return False

    @staticmethod
    def find_ports():
        global adc_count

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
                    ads = ADS.ADS1115(i2c, address=adr)
                    if DriverADS1115.is_ads111x(ads):
                        adc_count += 1
                        for ch in DriverADS1115.CHANNELS:
                            port_name = 'ADC #%d in %d' % (adc_count, ch)
                            port_cfg = {'adr': adr, 'cnt': adc_count, 'in': ch}
                            io_ports[port_name] = IoPort(PortFunc.Ain,
                                                         DriverADS1115,
                                                         port_cfg,
                                                         deps)
                    else:
                        log.brief('I²C device at 0x%02X seems not to be an ADS1x15, probably a different device, or already in use.', adr)
                except Exception as ex:
                    log.debug('%r', ex)
                    # pass  # whatever it is, ignore this device
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

    def __init__(self, cfg, func):
        super().__init__(cfg, func)
        self.name = 'ADC #%d (ADS1115 @0x%02X) in %d' % (cfg['cnt'], cfg['adr'], cfg['in'])
        self.cfg = cfg

        self.gain = cfg.get('gain', -16)
        i2c = busio.I2C(board.SCL, board.SDA)
        self._ads = ADS.ADS1115(i2c, address=cfg['adr'], gain=(abs(self.gain)))
        self._ana_in = AnalogIn(self._ads, cfg['in'])

    def close(self):
        if self._fake:
            return super().close()

        # return chip to power-on defaults to allow future auto-detect
        self._ads.gain = 2
        self._ads.read(0, is_differential=True)

    def read(self):
        if self._fake:
            return super().read()

        self._adjust_gain()
        # val = self._ana_in.voltage
        median = [self._ana_in.voltage,
                  self._ana_in.voltage,
                  self._ana_in.voltage,
                  self._ana_in.voltage,
                  self._ana_in.voltage]
        median.sort()
        log.debug('median %f %f %f', median[0], median[2], median[4])
        val = median[2]

        return val

    def _adjust_gain(self):
        """ gain <= 0 is auto-gain.
            Since there's only a common gain for all channels,
            we need repeated conversions, and increase I2C traffic.
        """
        ads = self._ads
        ads.gain = abs(self.gain)
        if self.gain <= 0:
            val = self._ana_in.value
            while abs(val) > 32300:
                l_gain = [ads.gains[0]] + [g for g in ads.gains if g < ads.gain]
                ads.gain = l_gain[-1]
                val = self._ana_in.value
            while abs(val) < 16000:
                h_gain = [g for g in ads.gains if g < ads.gain] + [ads.gains[-1]]
                ads.gain = h_gain[0]
                val = self._ana_in.value
            self.gain = -ads.gain
            log.debug('ADS gain %d (%d), digits %f', ads.gain, self.gain, val)

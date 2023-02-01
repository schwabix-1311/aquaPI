#!/usr/bin/env python3

import logging
import random

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    #import adafruit_ads1x15.ads1015 as ADSxx
    from adafruit_ads1x15.analog_in import AnalogIn

    SIMULATED = False
except NotImplementedError:
    SIMULATED = True

from .base import (InDriver, IoPort, PortFunc)

log = logging.getLogger('DriverADS111x')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)



# ========== ADC inputs ==========


class DriverADC(InDriver):
    """ Base class for all AnalogDigitalConverters (ADC)
        You should not need to interact explicitly with derived classes,
        auto-detection returns appropriate objects in IoPorts
    """
    @staticmethod
    def find_ports():
        io_ports = {}
        if not SIMULATED:
            # autodetect of I²C is undefined and risky, as some chips may react
            # on read as if it was a write! We're on a pretty well defined HW though.
            cnt = 0
            i2c = busio.I2C(board.SCL, board.SDA)
            deps = ['GPIO %d in' % board.SCL, 'GPIO %d out' % board.SCL
                   , 'GPIO %d in' % board.SDA, 'GPIO %d out' % board.SDA]

            # one loop for each chip type
            for adr in DriverADS1115.ADDRESSES:
                try:
                    log.brief('Scanning I²C bus for ADS1x13/4/5 ...')
                    ads = ADS.ADS1115(i2c, address=adr)
                    if DriverADS1115.is_ads111x(ads):
                        cnt += 1
#           for ch in DriverADS1115.CHANNELS:
                        for ch in [ ADS.P0, ADS.P1, ADS.P2, ADS.P3 ]:
                            port_name = 'ADC #%d ch %d' % (cnt, ch)
                            io_ports[port_name] = IoPort( PortFunc.Ain,
                                                          DriverADS1115,
                                                          {'adr': adr, 'cnt': cnt, 'ch': ch},
                                                          deps )
                    else:
                        log.brief('I²C device at 0x%02X seems not to be an ADS1x15, probably a different device, or already in use.', adr)
                except Exception as ex:
                    log.debug('%r', ex)
                    #pass  # whatever it is, ignore this device
        else:
            deps = ['GPIO 2 in', 'GPIO 2 out']
            # name: IoPort(portFunction, drvClass, configDict, dependantsArray)
            io_ports = {
                'ADC #1 ch 0': IoPort(PortFunc.Ain, DriverADC, {'cnt': 1, 'ch': 0, 'fake': True}, deps),
                'ADC #1 ch 1': IoPort(PortFunc.Ain, DriverADC, {'cnt': 1, 'ch': 1, 'fake': True}, deps),
                'ADC #1 ch 2': IoPort(PortFunc.Ain, DriverADC, {'cnt': 1, 'ch': 2, 'fake': True}, deps),
                'ADC #1 ch 3': IoPort(PortFunc.Ain, DriverADC, {'cnt': 1, 'ch': 3, 'fake': True}, deps)
            }
        return io_ports

    def __init__(self, func, cfg):
        super().__init__(func, cfg)
        self.func = func
        self.name = 'ADC #%d ch %d' % (cfg['cnt'], cfg['ch'])
        if self._fake:
            self.name = '!' + self.name

        if not self._fake:
            self.gain = cfg['gain'] or 0
            i2c = busio.I2C(board.SCL, board.SDA)
            self._ads = ADS.ADS1115(i2c, address=cfg['adr'], gain=(self.gain or 2))
            self._ana_in = AnalogIn(self._ads, cfg['pga'])

    def __del__(self):  # ??
        self.close()

    def close(self):
        log.debug('Closing %r', self)

    def read(self):
        val = False if random.random() <= 0.5 else True
        log.info('%s = %d', self.name, val)
        return val


class DriverADS1115(DriverADC):
    """ A driver for TI's 16bit ADC ADS1113/4/5, and 12bit ADS1013/4/5
        # back to defaults to enable our auto-datect
        Chip variants:
            ADS1x13 1 channel, no comparator
            ADS1x14 1 channel, gain adjustable
            ADS1x15 4 channel or 2 differential, gain adjustable
        Sample rate and continuous mode are not supported. Differential is not yet ...
    """

    ADDRESSES = [ 0x48, 0x49, 0x4A, 0x4B ]
    #CHANNELS = [ P0, P1, P2, P3 ]  # currently only grounded, no differential channels

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
                # default is: ch 0-1 differential, gain 2, 1 shot, 128SPS, comp low, no latch, disable comp
                if buf[2:7] == [0x85, 0x83, 0x80, 0x00, 0x7F, 0xFF]:
                    return True
                log.debug('I²C device @ 0x%02X returns 0x%04X 0x%04X 0x%04X from reg 1..3, probably a different device, or already in use.'
                         , device.device_address, buf[2:3], buf[4:5], buf[6:7] )
        except Exception as ex:
            log.debug('Exception %r', ex)
            #pass  # whatever it is, ignore device @ this adr!
        return False


    def __init__(self, func, cfg):
        super().__init__(func, cfg)
        self.name = 'ADC #%d (ADS1115 @0x%02X) ch %d' % (cfg['cnt'], cfg['adr'], cfg['ch'])
        self.cfg = cfg

        self.gain = cfg['gain'] or -16
        i2c = busio.I2C(board.SCL, board.SDA)
        self._ads = ADS.ADS1115(i2c, address=cfg['adr'], gain=(abs(self.gain)))
        self._ana_in = AnalogIn(self._ads, cfg['pga'])

    def close(self):
        # return chip to power-on defaults to allow future auto-detect
        self._ads.gain = 2
        self._ads.read(0, is_differential=True)

    def read(self):
        self._adjust_gain()
        val = self._ana_in.voltage
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

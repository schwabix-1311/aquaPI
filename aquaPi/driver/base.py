#!/usr/bin/env python3

import logging
from os import path
from enum import Enum
from collections import namedtuple
import math
import random

log = logging.getLogger('driver.base')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


# ========== common functions ==========


def is_raspi():
    model = ''
    if path.exists('/sys/firmware/devicetree/base/model'):
        with open('/sys/firmware/devicetree/base/model', 'r', encoding='utf-8') as f:
            model = f.readline()
    return 'raspberry' in model.lower()


# ========== Exceptions ==========


class DriverNYI(Exception):
    def __init__(self, msg='Not yet implemented.'):
        super().__init__()
        self.msg = msg


class DriverParamError(Exception):
    def __init__(self, msg='Invalid parameter value.'):
        super().__init__()
        self.msg = msg


class DriverInvalidAddrError(Exception):
    def __init__(self, msg=None, adr=None):
        if not msg:
            msg = 'Pin, channel or address %r does not exist.' % adr
        super().__init__()
        self.msg = msg


class DriverPortInuseError(Exception):
    def __init__(self, msg=None, port=None):
        if not msg:
            msg = 'Pin or channel %r is already assigned.' % port
        super().__init__()
        self.msg = msg


class DriverReadError(Exception):
    def __init__(self, msg='Failed to read a valid value.'):
        super().__init__()
        self.msg = msg


class DriverWriteError(Exception):
    def __init__(self, msg='Failed to write value to the output.'):
        super().__init__()
        self.msg = msg


# ========== common types ==========


IoPort = namedtuple('IoPort', 'func driver cfg deps used', defaults=([], 0))


class PortFunc(Enum):
    """ Function of a port driver: Bool/Analog/String + In/Out
    """
    Bin, Bout, Ain, Aout, Sin, Sout = range(1, 7)


class PinFunc(Enum):
    UNKNOWN = -1
    OUT = 0
    IN = 1
    SERIAL = 40
    SPI = 41
    I2C = 42
    PWM = 43


# ========== driver base classes ==========


class Driver:
    """ base class of all drivers
        Drivers persist their cinfiguration in dict 'cfg', no need for
        __getstate__/__setstate__ overloads in derived classes.
    """

    # TODO this persistance approach could be transferred to MsgNodes!
    def __init__(self, cfg, func):
        self.name = '!abstract'
        self.cfg = cfg
        self.func = func
        self._fake = not is_raspi()
        if 'fake' in cfg:
            self._fake |= bool(cfg['fake'])

    def __del__(self):  # ??
        self.close()

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.cfg)

    def close(self):
        log.debug('Closing %r', self)


class InDriver(Driver):
    """ base class of all input drivers
        InDriver can be read, e.g. a temperature sensor.
    """

    def __init__(self, cfg, func):
        super().__init__(cfg, func)
        self.name = '!abstract IN'
        self._interval = 0

    def read(self):
        return 0.0


class AInDriver(InDriver):
    """ Base class for all AnalogDigitalConverters (ADC)
    """
    def __init__(self, cfg, func):
        super().__init__(cfg, func)
        self.name = '!ADC in'
        self.initval = cfg.get('initval', None)
        self._val = self.initval
        self._dir = 1

    def read(self):
        rnd = random.random()
        if rnd < .1:
            self._dir = math.copysign(1, self.initval - self._val)
        elif rnd > .7:
            self._val += 0.05 * self._dir
        self._val = round(min(max(self.initval - 1, self._val), self.initval + 1), 2)
        log.info('%s = %f', self.name, self._val)
        return float(self._val)


class OutDriver(Driver):
    """ base of all output drivers
        OutDriver can be written, the last written value can be read.
    """

    def __init__(self, cfg, func):
        super().__init__(cfg, func)
        self.name = '!abstract OUT'
        self._val = 0

    def write(self, value):
        self._val = value

    def read(self):
        return self._val

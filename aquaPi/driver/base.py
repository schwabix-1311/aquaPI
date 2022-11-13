#!/usr/bin/env python3

import logging
from os import path
from enum import Enum
from collections import namedtuple

log = logging.getLogger('Driver Base')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


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
        super().__init__(msg)


class DriverParamError(Exception):
    def __init__(self, msg='Invalid parameter value.'):
        super().__init__(msg)


class DriverInvalidAddrError(Exception):
    def __init__(self, msg=None, adr=None):
        if not msg:
            msg = 'Pin, channel or address %r does not exist.' % adr
        super().__init__(msg)


class DriverPortInuseError(Exception):
    def __init__(self, msg=None, port=None):
        if not msg:
            msg = 'Pin or channel %r is already assigned.' % port
        super().__init__(msg)


class DriverReadError(Exception):
    def __init__(self, msg='Failed to read a valid value.'):
        super().__init__(msg)


class DriverWriteError(Exception):
    def __init__(self, msg='Failed to write value to the output.'):
        super().__init__(msg)


# ========== common types ==========


IoPort = namedtuple('IoPort', ['function', 'driver', 'cfg'])


class PortFunc(Enum):
    IO, IN, OUT, PWM, ADC = range(1, 6)


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
    def __init__(self, func, cfg):
        self.name = '!abstract'
        self.func = func
        self.cfg = cfg
        self._fake = not is_raspi()
        if 'fake' in cfg:
            self._fake |= bool(cfg['fake'])

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.cfg)


class InDriver(Driver):
    """ base class of all input drivers
        InDriver can be read, e.g. a temperature sensor.
    """

    def __init__(self, func, cfg):
        super().__init__(func, cfg)
        self.name = '!abstract IN'
        self._interval = 0

    def read(self):
        return 0.0


class OutDriver(Driver):
    """ base of all output drivers
        OutDriver can be written, the last written value can be read.
    """

    def __init__(self, func, cfg):
        super().__init__(func, cfg)
        self.name = '!abstract OUT'
        self._val = 0

    def write(self, value):
        self._val = value

    def read(self):
        return self._val

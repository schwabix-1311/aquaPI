#!/usr/bin/env python3

import logging
from typing import Any
from os import path
from enum import Enum
from collections import namedtuple
import math
import random

log = logging.getLogger('driver.base')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


# ========== common functions ==========


def is_raspi() -> bool:
    model: str = ''
    model_inf: str = '/sys/firmware/devicetree/base/model'
    if path.exists(model_inf):
        with open(model_inf, 'r', encoding='utf-8') as f:
            model = f.readline()
    return 'raspberry' in model.lower()


# ========== Exceptions ==========


class DriverError(Exception):
    def __init__(self, msg):
        super().__init__()
        self.msg: str = msg


class DriverNYI(DriverError):
    def __init__(self, msg: str = 'Not yet implemented.'):
        super().__init__(msg)


class DriverParamError(DriverError):
    def __init__(self, msg: str = 'Invalid parameter value.'):
        super().__init__(msg)


class DriverInvalidAddrError(DriverError):
    def __init__(self, adr: Any, msg: str = ''):
        if not msg:
            msg = 'Pin, channel or address %r does not exist.' % adr
        super().__init__(msg)


class DriverInvalidPortError(DriverError):
    def __init__(self, port: Any, msg: str = ''):
        if not msg:
            msg = 'There is no port named "%s"' % port
        super().__init__(msg)


class DriverPortInuseError(DriverError):
    def __init__(self, port: Any, msg: str = ''):
        if not msg:
            msg = 'Pin or channel %r is already assigned.' % port
        super().__init__(msg)


class DriverReadError(DriverError):
    def __init__(self, msg: str = 'Failed to read a valid value.'):
        super().__init__(msg)


class DriverWriteError(DriverError):
    def __init__(self, msg: str = 'Failed to write value to the output.'):
        super().__init__(msg)


class DriverConfigError(DriverError):
    def __init__(self, msg: str = 'Failed to send message'):
        super().__init__(msg)


# ========== common types ==========


IoPort = namedtuple('IoPort', 'func driver cfg deps used', defaults=([], 0))


class PortFunc(Enum):
    """ Function of a port driver: Bool/Analog/Text + In/Out
    """
    Bin, Bout, Ain, Aout, Tin, Tout = range(1, 7)


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
    def __init__(self, cfg: dict[str, str], func: PortFunc):
        self.name: str = '!abstract'
        self.cfg: dict[str, str] = cfg
        self.func: PortFunc = func
        self._fake: bool = not is_raspi()
        if 'fake' in cfg:
            self._fake |= bool(cfg['fake'])

    def __del__(self) -> None:
        self.close()

    def __str__(self) -> str:
        return '{}({})'.format(type(self).__name__, self.cfg)

    def close(self) -> None:
        log.debug('Closing %r', self)


class InDriver(Driver):
    """ base class of all input drivers
        InDriver can be read, e.g. a temperature sensor.
    """

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self.namei: str = '!abstract IN'
        self._interval: int = 0

    def read(self) -> int | float:
        return 0


class AInDriver(InDriver):
    """ Base class for all AnalogDigitalConverters (ADC)
    """
    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self.name: str = '!ADC in'
        self.initval: float = float(cfg.get('initval', 0.0))
        self._val: float = self.initval
        self._dir: float = 1

    def read(self) -> float:
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
        OutDriver can be written to, the last written value can be read.
    """

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self.name: str = '!abstract OUT'
        self._val = 0.0

    def write(self, value) -> None:
        self._val = value

    def read(self):
        return self._val

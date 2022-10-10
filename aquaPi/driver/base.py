#!/usr/bin/env python3

import logging
from os import path
try:
    import RPi.GPIO as GPIO
except:
    pass


log = logging.getLogger('Driver Base')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
log.setLevel(logging.INFO)
log.setLevel(logging.DEBUG)


# ========== common functions ==========


def is_raspi():
    model = ''
    if path.exists('/sys/firmware/devicetree/model'):
        with open('/sys/firmware/devicetree/base/model', 'r') as f:
            model = f.readline()
    return 'raspberry' in model.lower()


_func_map = {-1: 'UNKNOWN', 0: 'OUT', 1: 'IN', 40: 'SERIAL', 41: 'SPI', 42: 'I2C', 43: 'PWM'}
_pins_available = None
_pins_unused = None

def init_pin_maps():
    global _pins_available, _pins_unused

    if not _pins_available:
        if is_raspi():
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            _pins_available = set()
            for i in range(28):
                try:
                    if GPIO.gpio_function(i) in [0, 1]:
                        _pins_available.add(i)
                    else:
                        log.info('pin %d is in use as %s' % (i, _func_map[GPIO.gpio_function(i)]))
                except:
                    log.debug('func pin %d = %d' % (i, GPIO.gpio_function(i)))
        else:
            # not a Raspi, simulate typical IO layout, skip I²C and PWM
            _pins_available = {0, 1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 25, 26, 27}
        log.brief('available GPIO pins: %r' % _pins_available)
        _pins_unused = _pins_available


def get_unused_pins():
    if not _pins_available or not _pins_unused:
        init_pin_maps()
    return _pins_unused


def set_pin_usage(pin, used):
    global _pins_available, _pins_unused

    if pin in _pins_available:
        if used:
            _pins_unused.remove(pin)
        else:
            _pins_unused.add(pin)
    else:
        log.error('assign/release an unavailable pin? (pin %d)' % pin)


# ========== base classes ==========


class DriverReadError(Exception):
    def __init__(self, msg=None):
        super().__init__(msg)


class Driver:
    """ base class of all drivers
    """
    def __init__(self, cfg):
        self.name = 'abstract'
        self.cfg = cfg

    def __getstate__(self):
        state = {'name': self.name, 'cfg': self.cfg}
        log.debug('Driver.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('Driver.setstate %r', state)
        self.__init__(state['cfg'])
        self.name = state['name']

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.cfg)


class InDriver(Driver):
    """ base class of all input drivers
        InDriver can be read, e.g. a temperature sensor.
    """
    def __init__(self, cfg):
        super().__init__(cfg)
        self.name = 'abstract IN'
        self._interval = 0

    # def __getstate__(self):
    #     state = super().__getstate__()
    #     return state

    # def __setstate__(self, state):
    #     log.debug('InDriver.setstate %r', state)
    #     self.__init__(state['cfg'])
    #     self.name = state['name']

    def read(self):
        return 0.0


class OutDriver(Driver):
    """ base of all output drivers
        OutDriver can be written, the last written value can be read.
    """
    def __init__(self, cfg):
        super().__init__(cfg)
        self.name = 'abstract OUT'
        self._state = 0


    # def __getstate__(self):
    #     state = {'name': self.name, 'cfg': self.cfg}
    #     log.debug('Driver.getstate %r', state)
    #     return state

    # def __setstate__(self, state):
    #     log.debug('Driver.setstate %r', state)
    #     self.__init__(state['cfg'])
    #     self.name = state['name']

    def write(self, state):
        gpio.output(self._pin, state)
        self._state = state

    def read(self):
        return self._state

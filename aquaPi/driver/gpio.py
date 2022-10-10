#!/usr/bin/env python3

import sys
import logging
import os
import random
try:
    import RPi.GPIO as GPIO
except:
    pass

from .base import *


log = logging.getLogger('Driver GPIO')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== GPIO ==========


class DriverGPIO(InDriver):
    """ abstrract base of GPIO drivers
    """
    @staticmethod
    def find():
        return get_unused_pins()

    def __init__(self, cfg):
        super().__init__(cfg)

        self._fake = not is_raspi()
        if 'fake' in cfg:
            self._fake |= bool(cfg['fake'])

        init_pin_maps()

        self._pin = int(cfg['pin'])
        if not self._pin in get_unused_pins():
            raise Exception('GPIO pin %d is already assigned.' % self._pin)
        set_pin_usage(self._pin, True)

    def close(self):
        if not self._fake:
            set_pin_usage(self._pin, False)
            GPIO.cleanup(self._pin)


class DriverGPIOin(DriverGPIO):
    """ single pin GPIO input
    """

    def __init__(self, cfg):
        super().__init__(cfg)
        self.name = 'GPIO in @ %d' % self._pin
        if not self._fake:
            GPIO.setup(self._pin, GPIO.IN)

    def read(self):
        if not self._fake:
            return GPIO.input(self._pin)
        else:
            log.info('read GPIO pin %d = %d' % (self._pin, self._val))
            return False if random.random() <= 0.5 else True


class DriverGPIOout(DriverGPIO):
    """ single pin GPIO output
    """
    def __init__(self, cfg):
        super().__init__(cfg)
        self.name = 'GPIO out @ %d' % self._pin
        if not self._fake:
            GPIO.setup(self._pin, GPIO.OUT)

        self.write(False)  #??

    def write(self, val):
        if not self._fake:
            GPIO.output(self._pin, bool(val))
        else:
            log.info('write GPIO pin %d = %d' % (self._pin, bool(val)))
            self._val = bool(val)

    def read(self):
        if not self._fake:
            return GPIO.input(self._pin)
        else:
            log.info('read GPIO pin %d = %d' % (self._pin, self._val))
            return self._val

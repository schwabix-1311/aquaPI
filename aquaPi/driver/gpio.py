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
        self._pin = int(cfg['pin'])
        assign_pin(self._pin, True)  # may raise exceptions: InvalidAddr|PortInuse

    def __del__(self):
        self.close()

    def close(self):
        log.debug('Closing %r' % self)
        if not self._fake and self._pin != None:
            assign_pin(self._pin, False)
            GPIO.cleanup(self._pin)
            self._pin = None


class DriverGPIOin(DriverGPIO):
    """ single pin GPIO input
    """

    def __init__(self, cfg):
        super().__init__(cfg)
        self.name = 'GPIOin @ %d' % self._pin
        if self._fake:
            self.name = '!' + self.name
        if not self._fake:
            GPIO.setup(self._pin, GPIO.IN)

    def read(self):
        if not self._fake:
            return GPIO.input(self._pin)
        else:
            log.info('%s = %d' % (self.name, self._val))
            return False if random.random() <= 0.5 else True


class DriverGPIOout(DriverGPIO):
    """ single pin GPIO output
    """
    def __init__(self, cfg):
        super().__init__(cfg)
        self.name = 'GPIOout @ %d' % self._pin
        if self._fake:
            self.name = '!' + self.name
        if not self._fake:
            GPIO.setup(self._pin, GPIO.OUT)

        self.write(False)

    def write(self, val):
        if not self._fake:
            GPIO.output(self._pin, bool(val))
        else:
            log.info('%s -> %d' % (self.name, bool(val)))
            self._val = bool(val)

    def read(self):
        if not self._fake:
            return GPIO.input(self._pin)
        else:
            log.info('%s = %d' % (self.name, self._val))
            return self._val

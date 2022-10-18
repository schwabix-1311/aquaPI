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


log = logging.getLogger('DriverGPIO')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


if is_raspi():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)


# ========== GPIO ==========


class DriverGPIO(OutDriver, InDriver):
    """ GPIO in & out driver
    """
    @staticmethod
    def find_ports():
        if not is_raspi() or True:
            # name: IoPort('function', 'driver', 'cfg')
            io_ports = { 'GPIO 0':  IoPort(PortFunc.IO, DriverGPIO, {'pin': 0, 'fake': True})
                       , 'GPIO 1':  IoPort(PortFunc.IO, DriverGPIO, {'pin': 1, 'fake': True})
                       , 'GPIO 12': IoPort(PortFunc.IO, DriverGPIO, {'pin': 12, 'fake': True}) }
        else:
            io_ports = {}
            cnt = 0
            for pin in range(28):
                try:
                    func = PinFunc(GPIO.gpio_function(pin))
                    if func in [PinFunc.IN, PinFunc.OUT]:
                        port_name = 'GPIO %d' % cnt
                        io_ports[port_name] = IoPort(PortFunc.IO, DriverGPIO, {'pin': pin})
                        cnt += 1
                    else:
                        log.debug('pin %d is in use as %s' % (pin, func.name))
                except:
                    log.debug('Unknown function on pin %d = %d' % (pin, GPIO.gpio_function(pin)))
        return io_ports

    def __init__(self, func, cfg):
        if func not in [PortFunc.IN, PortFunc.OUT]:
            raise DriverParamError('This driver supports IN or OUT, nothing else.')

        super().__init__(func, cfg)
        self.func = func
        self._pin = int(cfg['pin'])
        self.name = 'GPIO %s @ %d' % (func.name, self._pin)
        if self._fake:
            self.name = '!' + self.name

        if not self._fake:
            GPIO.setup(self._pin, GPIO.IN if self.func==PortFunc.IN else GPIO.OUT)

    def __del__(self):
        self.close()

    def close(self):
        log.debug('Closing %r' % self)
        if not self._fake and self._pin != None:
            GPIO.cleanup(self._pin)
            self._pin = None

    def write(self, val):
        if self.func == PortFunc.IN:
            raise DriverWriteError()

        if not self._fake:
            GPIO.output(self._pin, bool(val))
        else:
            log.info('%s -> %d' % (self.name, bool(val)))
            self._val = bool(val)

    def read(self):
        if not self._fake:
            val = GPIO.input(self._pin)
        else:
            if self.func == PortFunc.IN:
                val = False if random.random() <= 0.5 else True
            else:
               val = self._val
            log.info('%s = %d' % (self.name, val))
        return val

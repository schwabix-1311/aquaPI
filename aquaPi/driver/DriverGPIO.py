#!/usr/bin/env python3

import logging
import random
try:
    import RPi.GPIO as GPIO
except RuntimeError:
    # make lint happy with minimal non-funct facade
    class GPIOdummy():
        BCM = None
        IN = None
        OUT = None
        @staticmethod
        def setwarnings(warn):
            warn = not warn
        @staticmethod
        def gpio_function(pin):
            pin = not pin
            return None
        @staticmethod
        def setmode(mode):
            mode = not mode
        @staticmethod
        def setup(pin, mode):
            pin = not pin
            mode = not mode
        @staticmethod
        def cleanup(pin):
            pin = not pin
        @staticmethod
        def input(pin):
            return pin
        @staticmethod
        def output(pin, value):
            pin = not pin
            value = not value
    GPIO = GPIOdummy

from .base import (InDriver, OutDriver, IoPort, PortFunc, PinFunc, is_raspi, DriverParamError, DriverWriteError)


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
        if not is_raspi():
            # name: IoPort('function', 'driver', 'cfg')
            io_ports = { 'GPIO 0':  IoPort(PortFunc.IO, DriverGPIO, {'pin': 0, 'fake': True})
                       , 'GPIO 1':  IoPort(PortFunc.IO, DriverGPIO, {'pin': 1, 'fake': True})
                       , 'GPIO 12': IoPort(PortFunc.IO, DriverGPIO, {'pin': 12, 'fake': True}) }
        else:
            io_ports = {}
            for pin in range(28):
                try:
                    func = PinFunc(GPIO.gpio_function(pin))
                    if func in [PinFunc.IN, PinFunc.OUT]:
                        port_name = 'GPIO %d' % pin
                        io_ports[port_name] = IoPort(PortFunc.IO, DriverGPIO, {'pin': pin})
                    else:
                        log.debug('pin %d is in use as %s', pin, func.name)
                except KeyError:
                    log.debug('Unknown function on pin %d = %d', pin, GPIO.gpio_function(pin))
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
        log.debug('Closing %r', self)
        if not self._fake and self._pin != None:
            GPIO.cleanup(self._pin)
            self._pin = None

    def write(self, value):
        if self.func == PortFunc.IN:
            raise DriverWriteError()

        if not self._fake:
            GPIO.output(self._pin, bool(value))
        else:
            log.info('%s -> %d', self.name, bool(value))
            self._val = bool(value)

    def read(self):
        if not self._fake:
            val = GPIO.input(self._pin)
        else:
            if self.func == PortFunc.IN:
                val = False if random.random() <= 0.5 else True
            else:
                val = self._val
            log.info('%s = %d', self.name, val)
        return val

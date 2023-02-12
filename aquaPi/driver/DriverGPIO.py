#!/usr/bin/env python3

import logging
import random

try:
    import RPi.GPIO as GPIO
except (RuntimeError, ModuleNotFoundError):
    # make lint happy with minimal non-funct facade
    class GPIOdummy:
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

from .base import (InDriver, OutDriver, IoPort, PortFunc, PinFunc, is_raspi, DriverWriteError)

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
        io_ports = {}
        if is_raspi():
            for pin in range(28):
                try:
                    # the dependants list would allow to offer GPIOs that are not yet in use by their other function
                    func = PinFunc(GPIO.gpio_function(pin))
                    if func in [PinFunc.IN, PinFunc.OUT]:
                        port_name = 'GPIO %d ' % pin
                        io_ports[port_name + 'in'] = IoPort( PortFunc.Bin,
                                                             DriverGPIO,
                                                             {'pin': pin},
                                                             [] )
                        io_ports[port_name + 'out'] = IoPort( PortFunc.Bout,
                                                              DriverGPIO,
                                                              {'pin': pin},
                                                              [] )
                    else:
                        log.debug('pin %d is in use as %s', pin, func.name)
                except KeyError:
                    log.debug('Unknown function on pin %d = %d', pin, GPIO.gpio_function(pin))
        else:
            # name: IoPort(portFunction, drvClass, configDict, dependantsArray)
            io_ports = {
                'GPIO 0 in': IoPort(PortFunc.Bin, DriverGPIO, {'pin': 0, 'fake': True}, []),
                'GPIO 0 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 0, 'fake': True}, []),
                'GPIO 1 in': IoPort(PortFunc.Bin, DriverGPIO, {'pin': 1, 'fake': True}, []),
                'GPIO 1 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 1, 'fake': True}, []),
                'GPIO 18 in': IoPort(PortFunc.Bin, DriverGPIO, {'pin': 18, 'fake': True}, []),
                'GPIO 18 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 18, 'fake': True}, [])
            }
        return io_ports

    def __init__(self, func, cfg):
        super().__init__(func, cfg)
        self.func = func
        self._pin = int(cfg['pin'])
        self.name = 'GPIO %d %s' % (self._pin, 'in' if func==PortFunc.Bin else 'out')

        if not self._fake:
            GPIO.setup(self._pin, GPIO.IN if func==PortFunc.Bin else GPIO.OUT)
        else:
            self.name = '!' + self.name

    def __del__(self):
        self.close()

    def close(self):
        log.debug('Closing %r', self)
        if not self._fake and self._pin is not None:
            GPIO.cleanup(self._pin)
            self._pin = None

    def write(self, value):
        if self.func == PortFunc.Bin:
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
            if self.func == PortFunc.Bin:
                val = False if random.random() <= 0.5 else True
            else:
                val = self._val
            log.info('%s = %d', self.name, val)
        return val

#!/usr/bin/env python3

import logging
import random

#TODO: replace all with Adafruit Ports, keep unique GPIO.gpio_function
try:
    import RPi.GPIO as GPIO  # type: ignore[import-untyped]
except (RuntimeError, ModuleNotFoundError):
    # make lint happy with minimal non-funct facade
    class GPIO:  # type: ignore[no-redef]
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

from .base import (InDriver, OutDriver, IoPort, PortFunc, is_raspi, DriverWriteError)

log = logging.getLogger('driver.DriverGPIO')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


if is_raspi():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)


# ========== GPIO ==========


class DriverGPIO(OutDriver, InDriver):
    """ GPIO in & out driver
    """

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        io_ports = {}
        if is_raspi():
            for pin in range(28):
                try:
                    # func = PinFunc(GPIO.gpio_function(pin))
                    port_name = 'GPIO %d ' % pin
                    io_ports[port_name + 'in'] = IoPort(PortFunc.Bin,
                                                        DriverGPIO,
                                                        {'pin': pin},
                                                        [])
                    io_ports[port_name + 'out'] = IoPort(PortFunc.Bout,
                                                         DriverGPIO,
                                                         {'pin': pin},
                                                         [])
                except KeyError:
                    log.debug('Unknown function on pin %d = %d',
                              pin, GPIO.gpio_function(pin))
        else:
            # name: IoPort(portFunction, drvClass, configDict, dependantsArray)
            # need all that are simulated somewhere - devices or dependencies
            io_ports = {
                'GPIO 0 in': IoPort(PortFunc.Bin, DriverGPIO, {'pin': 0, 'fake': True}, []),
                'GPIO 0 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 0, 'fake': True}, []),
                'GPIO 1 in': IoPort(PortFunc.Bin, DriverGPIO, {'pin': 1, 'fake': True}, []),
                'GPIO 1 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 1, 'fake': True}, []),
                'GPIO 2 in': IoPort(PortFunc.Bin, DriverGPIO, {'pin': 2, 'fake': True}, []),
                'GPIO 2 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 2, 'fake': True}, []),
                'GPIO 4 in': IoPort(PortFunc.Bin, DriverGPIO, {'pin': 4, 'fake': True}, []),     # 1-wire
                'GPIO 4 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 4, 'fake': True}, []),   # 1-wire
                'GPIO 12 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 12, 'fake': True}, []),  # Heater relay
                'GPIO 18 in': IoPort(PortFunc.Bin, DriverGPIO, {'pin': 18, 'fake': True}, []),
                'GPIO 18 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 18, 'fake': True}, []),  # PWM 0
                'GPIO 19 in': IoPort(PortFunc.Bin, DriverGPIO, {'pin': 19, 'fake': True}, []),
                'GPIO 19 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 19, 'fake': True}, []),  # PWM 1
                'GPIO 20 out': IoPort(PortFunc.Bout, DriverGPIO, {'pin': 20, 'fake': True}, [])  # CO2 vent
            }
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self._pin: int | None = int(cfg['pin'])
        inout = 'in' if self._is_input_driver() else 'out'
        self.name: str = 'GPIO %d %s' % (self._pin, inout)

        if not self._fake:
            GPIO.setup(self._pin, GPIO.IN if inout == 'in' else GPIO.OUT)
        else:
            self.name = '!' + self.name

    def _is_input_driver(self) -> bool:
        return self.func == PortFunc.Bin

    def close(self) -> None:
        log.debug('Closing %r', self)
        if not self._fake and self._pin is not None:
            GPIO.cleanup(self._pin)
            self._pin = None

    def write(self, value: bool) -> None:
        if self._is_input_driver():
            raise DriverWriteError()

        log.info('%s -> %d', self.name, bool(value))
        if not self._fake:
            GPIO.output(self._pin, bool(value))
        self._val = bool(value)

    def read(self) -> bool:
        if not self._fake:
            self._val = GPIO.input(self._pin)
        else:
            if self._is_input_driver():
                self._val = False if random.random() <= 0.5 else True

        log.info('%s = %d', self.name, self._val)
        return bool(self._val)

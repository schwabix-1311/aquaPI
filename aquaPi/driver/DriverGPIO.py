#!/usr/bin/env python3

import logging
import random

try:
    import RPi.GPIO as GPIO  # type: ignore[import-untyped]
except (RuntimeError, ModuleNotFoundError):
    # minimal facade for non-Raspi systems, only fake drivers exist there
    class GPIO:  # type: ignore[no-redef]
        BCM = IN = OUT = None

        @staticmethod
        def setwarnings(*_): pass

        @staticmethod
        def setmode(*_): pass

        @staticmethod
        def setup(*_): pass

        @staticmethod
        def cleanup(*_): pass

        @staticmethod
        def input(*_): return 0

        @staticmethod
        def output(*_): pass

from .base import (InDriver, OutDriver, IoPort, PortFunc, is_raspi, DriverWriteError)

log = logging.getLogger('driver.DriverGPIO')


if is_raspi():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)


# ========== GPIO ==========


class DriverGPIO(OutDriver, InDriver):
    """ GPIO in & out driver
    """

    _BUS = 'GPIO'

    # simulated pins: everything some fake device or dependency needs
    #   0..2 (I²C on 2), 4 1-Wire, 12 heater relay, 13 filter pump,
    #   18/19 PWM 0/1, 20 CO2 valve
    _FAKE_IN_PINS = (0, 1, 2, 4, 13, 18, 19)
    _FAKE_OUT_PINS = (0, 1, 2, 4, 12, 13, 18, 19, 20)

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        if is_raspi():
            log.info('Scanning GPIO ports ...')
            in_pins = out_pins = range(28)
            cfg = {}
        else:
            log.info('Faking GPIO ports ...')
            in_pins, out_pins = DriverGPIO._FAKE_IN_PINS, DriverGPIO._FAKE_OUT_PINS
            cfg = {'fake': True}

        io_ports = {}
        for pin in sorted(set(in_pins) | set(out_pins)):
            # a pin is either input or output: 'in' depends on 'out', so
            # the registry refuses the second claim in either order
            if pin in in_pins:
                deps = [f'GPIO {pin} out'] if pin in out_pins else []
                io_ports[f'GPIO {pin} in'] = IoPort(PortFunc.Bin, DriverGPIO,
                                                    {'pin': pin, **cfg}, deps)
            if pin in out_pins:
                io_ports[f'GPIO {pin} out'] = IoPort(PortFunc.Bout, DriverGPIO,
                                                     {'pin': pin, **cfg}, [])
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self._pin: int | None = int(cfg['pin'])
        inout = 'in' if self._is_input_driver() else 'out'
        self.name = self._mark_fake(f'GPIO {self._pin} {inout}')
        if not self._fake:
            GPIO.setup(self._pin, GPIO.IN if inout == 'in' else GPIO.OUT)

    def _is_input_driver(self) -> bool:
        return self.func == PortFunc.Bin

    def _do_close(self) -> None:
        if not self._fake and self._pin is not None:
            GPIO.cleanup(self._pin)
            self._pin = None

    def write(self, value: bool) -> None:
        if self._is_input_driver():
            raise DriverWriteError()

        log.verbose('%s -> %d', self.name, bool(value))
        if not self._fake:
            GPIO.output(self._pin, bool(value))
        self._val = bool(value)

    def read(self) -> bool:
        if not self._fake:
            self._val = GPIO.input(self._pin)
        elif self._is_input_driver():
            self._val = random.random() > 0.5

        log.verbose('%s = %d', self.name, self._val)
        return bool(self._val)

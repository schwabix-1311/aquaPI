#!/usr/bin/env python3

import logging
from os import path
from time import sleep

try:
    from RPi.GPIO import gpio_function  # type: ignore[import-untyped]
except (RuntimeError, ModuleNotFoundError):
    # make lint happy with minimal non-funct facade
    def gpio_function(_: int):
        return 0

from .base import (OutDriver, IoPort, PortFunc, PinFunc, is_raspi, gpio_deps)


log = logging.getLogger('driver.DriverPWM')


# ========== PWM ==========


class DriverPWM(OutDriver):
    """ one PWM channel, hardware PWM
    """

    _BUS = 'PWM'
    PWMCHIP = '/sys/class/pwm/pwmchip0'
    PERIOD_NS = 3333333     # 300 Hz

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        io_ports = {}
        if is_raspi():
            log.info('Scanning PWM ports ...')
            cnt = 0
            for pin in range(28):
                try:
                    func = PinFunc(gpio_function(pin))
                except ValueError:
                    log.debug('Unknown function on pin %d = %d', pin, gpio_function(pin))
                    continue
                if func == PinFunc.PWM:
                    io_ports[f'PWM {cnt}'] = IoPort(PortFunc.Aout, DriverPWM,
                                                    {'pin': pin, 'channel': cnt},
                                                    gpio_deps(pin))
                    cnt += 1
        else:
            log.info('Faking PWM ports ...')
            io_ports = {
                f'PWM {ch}': IoPort(PortFunc.Aout, DriverPWM,
                                    {'pin': pin, 'channel': ch, 'fake': True},
                                    gpio_deps(pin))
                for ch, pin in enumerate((18, 19))
            }
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self._channel: int = int(cfg['channel'])
        self._pin: int = int(cfg['pin'])

        if self._fake:
            self.name = self._mark_fake(f'PWM {self._channel} @ pin {self._pin}')
        else:
            self.name = f'PWM {self._channel} @ sysfs'
            self._pwmchannel: str = path.join(self.PWMCHIP, f'pwm{self._channel}')

            if not path.exists(self._pwmchannel):
                log.debug('Creating sysfs PWM channel %d ...', self._channel)
                self._sysfs_write(path.join(self.PWMCHIP, 'export'), self._channel)
                sleep(.5)  # somebody (kernel?) needs a bit of time to finish it!
                if not path.exists(self._pwmchannel):
                    log.fatal('Unable to create sysfs PWM channel %d', self._channel)
                log.debug('Created sysfs PWM channel %d', self._channel)

            self._sysfs_write(path.join(self._pwmchannel, 'period'), self.PERIOD_NS)
            self._sysfs_write(path.join(self._pwmchannel, 'enable'), 0)

        self.write(0)

    @staticmethod
    def _sysfs_write(file: str, value: int) -> None:
        with open(file, 'wt', encoding='ascii') as f:
            f.write(str(value))

    def _do_close(self) -> None:
        if not self._fake:
            self._sysfs_write(path.join(self._pwmchannel, 'enable'), 0)
            log.debug('Disabled sysfs PWM channel %d', self._channel)

    def write(self, value: float) -> None:
        log.verbose('%s -> %f', self.name, float(value))
        if not self._fake:
            if not path.exists(self._pwmchannel):
                log.error('sysfs PWM channel %d vanished, skipping write', self._channel)
                return
            self._sysfs_write(path.join(self._pwmchannel, 'duty_cycle'),
                              int(value / 100.0 * self.PERIOD_NS))
            self._sysfs_write(path.join(self._pwmchannel, 'enable'), 1 if value > 0 else 0)
        self._val = float(value)

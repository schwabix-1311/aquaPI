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

from .base import (OutDriver, IoPort, PortFunc, PinFunc, is_raspi)


log = logging.getLogger('driver.DriverPWM')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== PWM ==========


class DriverPWMbase(OutDriver):
    """ abstract base of PWM drivers
    """

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self._channel: int = int(cfg['channel'])
        self._pin: int = int(cfg['pin'])


class DriverPWM(DriverPWMbase):
    """ one PWM channel, hardware PWM
    """

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        io_ports = {}
        if is_raspi():
            cnt = 0
            for pin in range(28):
                try:
                    func = PinFunc(gpio_function(pin))
                    if func == PinFunc.PWM:
                        deps = ['GPIO %d in' % pin, 'GPIO %d out' % pin]
                        port_name = 'PWM %d' % cnt
                        io_ports[port_name] = IoPort(PortFunc.Aout,
                                                     DriverPWM,
                                                     {'pin': pin, 'channel': cnt},
                                                     deps)
                        cnt += 1
                    #else:
                    #    log.debug('pin %d is configured as %s', pin, func.name)
                except KeyError:
                    log.debug('Unknown function on pin %d = %d', pin, gpio_function(pin))
            # name: IoPort('function', 'driver', 'cfg', 'dependants')
        else:
            io_ports = {
                'PWM 0': IoPort(PortFunc.Aout, DriverPWM,
                                {'pin': 18, 'channel': 0, 'fake': True},
                                ['GPIO 18 in', 'GPIO 18 out']),
                'PWM 1': IoPort(PortFunc.Aout, DriverPWM,
                                {'pin': 19, 'channel': 1, 'fake': True},
                                ['GPIO 19 in', 'GPIO 19 out'])
            }
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)

        self.name: str = 'PWM %d @ pin %d' % (self._channel, self._pin)
        if not self._fake:
            self.name = 'PWM %d @ sysfs' % self._channel
            self._pwmchip: str = '/sys/class/pwm/pwmchip0'
            self._pwmchannel: str = path.join(self._pwmchip, 'pwm%d' % self._channel)

            if not path.exists(self._pwmchannel):
                log.debug('Creating sysfs PWM channel %d ...', self._channel)
                with open(path.join(self._pwmchip, 'export'), 'wt', encoding='ascii') as p:
                    p.write('%d' % self._channel)
                sleep(.1)  # sombody (kernel?) needs a bit of time to finish it!
                log.debug('Created sysfs PWM channel %d', self._channel)

            with open(path.join(self._pwmchannel, 'period'), 'wt', encoding='ascii') as p:
                p.write('3333333')
            with open(path.join(self._pwmchannel, 'enable'), 'wt', encoding='ascii') as p:
                p.write('0')
        else:
            self.name = '!' + self.name

        self.write(0)

    def close(self) -> None:
        log.debug('Closing %r', self)
        if not self._fake:
            with open(path.join(self._pwmchannel, 'enable'), 'wt', encoding='ascii') as p:
                p.write('0')
            log.debug('Removing sysfs PWM channel %d ...', self._channel)
            with open(path.join(self._pwmchip, 'unexport'), 'wt', encoding='ascii') as p:
                p.write('%d' % self._channel)
            log.debug('Removed sysfs PWM channel %d', self._channel)

    def write(self, value:float) -> None:
        log.info('%s -> %f', self.name, float(value))
        if not self._fake:
            with open(path.join(self._pwmchannel, 'duty_cycle'), 'wt', encoding='ascii') as p:
                p.write('%d' % int(value / 100.0 * 3333333))
            with open(path.join(self._pwmchannel, 'enable'), 'wt', encoding='ascii') as p:
                p.write('1' if value > 0 else '0')
        self._val = float(value)

#!/usr/bin/env python3

import logging
from os import path

try:
    import RPi.GPIO as GPIO
except (RuntimeError, ModuleNotFoundError):
    # make lint happy with minimal non-funct facade
    class GPIOdummy:
        @staticmethod
        def gpio_function(pin):
            pin = not pin
            return None

    GPIO = GPIOdummy

from .base import (OutDriver, IoPort, PortFunc, PinFunc, is_raspi)

log = logging.getLogger('DriverPWM')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== PWM ==========


class DriverPWMbase(OutDriver):
    """ abstrract base of PWM drivers
    """

    def __init__(self, func, cfg):
        super().__init__(func, cfg)
        self._channel = int(cfg['channel'])
        self._pin = int(cfg['pin'])


class DriverPWM(DriverPWMbase):
    """ one PWM channel, hardware PWM
    """

    @staticmethod
    def find_ports():
        io_ports = {}
        if not is_raspi():
            # name: IoPort('function', 'driver', 'cfg', 'dependants')
            io_ports = {
                'PWM 0': IoPort(PortFunc.Aout, DriverPWM,
                                {'pin': 18, 'channel': 0, 'fake': True},
                                ['GPIO 18 in', 'GPIO 18 out']),
                'PWM 1': IoPort(PortFunc.Aout, DriverPWM,
                                {'pin': 19, 'channel': 1, 'fake': True},
                                ['GPIO 19 in', 'GPIO 19 out'])
            }
        else:
            cnt = 0
            for pin in range(28):
                try:
                    func = PinFunc(GPIO.gpio_function(pin))
                    if func == PinFunc.PWM:
                        deps = ['GPIO %d in' % pin, 'GPIO %d out' % pin]
                        port_name = 'PWM %d' % cnt
                        io_ports[port_name] = IoPort(PortFunc.Aout,
                                                     DriverPWM,
                                                     {'pin': pin, 'channel': cnt},
                                                     deps)
                        cnt += 1
                    else:
                        log.debug('pin %d is in use as %s', pin, func.name)
                except KeyError:
                    log.debug('Unknown function on pin %d = %d', pin, GPIO.gpio_function(pin))
        return io_ports

    def __init__(self, func, cfg):
        super().__init__(func, cfg)

        self.name = 'PWM %d @ pin %d' % (self._channel, self._pin)
        if not self._fake:
            self._sysfs = path.join('/sys/class/pwm/pwmchip0/pwm%d/' % self._channel)
            self.name = 'PWM %d @ sysfs' % self._channel
            with open(path.join(self._sysfs, 'enable'), 'wt', encoding='ascii') as p:
                p.write('0')
            with open(path.join(self._sysfs, 'period'), 'wt', encoding='ascii') as p:
                p.write('3333333')
        else:
            self.name = '!' + self.name

        self.write(0)

    def __del__(self):
        self.close()

    def close(self):
        log.debug('Closing %r', self)
        if not self._fake:
            with open(path.join(self._sysfs, 'enable'), 'wt', encoding='ascii') as p:
                p.write('0')

    def write(self, value):
        log.info('%s -> %f', self.name, float(value))
        if not self._fake:
            with open(path.join(self._sysfs, 'duty_cycle'), 'wt', encoding='ascii') as p:
                p.write('%d' % int(value / 100.0 * 3333333))
            with open(path.join(self._sysfs, 'enable'), 'wt', encoding='ascii') as p:
                p.write('1' if value > 0 else '0')
        else:
            self._val = float(value)


dummy = '''if False:
 This needs review to use IoPorts.dependants which solves implicit use of a different io_port
    class DriverSoftPWM(DriverPWMbase):
        """ one PWM channel, hardware PWM
            This is problematic, as it uses GPIO ports, thus should be handled by DriverGPIO, but then
            the PortFunc.IO is unexpected. Make PortFunc a set of PortFuncs and have a PortFunc.SoftPWM ?
        """
        @staticmethod
        def find_ports():
            if not is_raspi() or True:
                # name: IoPort('function', 'driver', 'cfg')
                io_ports = { 'softPWM 0':  IoPort(PortFunc.PWM, DriverSoftPWM, {'pin': 24, 'channel': 0, 'fake': True})
                           , 'softPWM 1':  IoPort(PortFunc.PWM, DriverSoftPWM, {'pin': 25, 'channel': 1, 'fake': True}) }
            else:
                io_ports = {}
                cnt = 0
                for pin in range(28):
                    try:
                        func = PinFunc(GPIO.gpio_function(pin))
                        if func in [PinFunc.PWM]:
                            port_name = 'softPWM %d' % cnt
                            io_ports[port_name] = IoPort(PortFunc.PWM, DriverPWM, {'pin': pin, 'channel': cnt})
                            cnt += 1
                        else:
                            log.debug('pin %d is in use as %s',  pin, func.name)
                    except KeyError:
                        log.debug('Unknown function on pin %d = %d', pin, GPIO.gpio_function(pin))
            return io_ports

        def __init__(self, func, cfg):
            super().__init__(func, cfg)

            self.name = 'SoftPWM %d @ pin %d' % (self._channel, self._pin)
            if not self._fake:
                GPIO.setup(self._pin, GPIO.OUT)
                self._pwm = GPIO.PWM(self._pin, 300)
                self._pwm.start(0)

            if self._fake:
                self.name = '!' + self.name

            self.write(0)

        def __del__(self):
            self.close()

        def close(self):
            log.debug('Closing %r', self)
            if not self._fake:
                self._pwm.stop()
                GPIO.cleanup(self._pin)

        def write(self, value):
            log.info('%s -> %f', self.name, float(value))
            if not self._fake:
                self._pwm.ChangeDutyCycle(float(value))
            else:
                self._val = float(value)
'''

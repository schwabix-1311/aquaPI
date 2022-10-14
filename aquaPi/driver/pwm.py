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


log = logging.getLogger('Driver PWM')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== GPIO ==========


class DriverPWMbase(Driver):
    """ abstrract base of PWM drivers
    """
    @staticmethod
    def find():
        return get_unused_pwms()

    def __init__(self, cfg):
        super().__init__(cfg)
        self._channel = int(cfg['channel'])


class DriverPWM(DriverPWMbase):
    """ one PWM channel, currently software PWM :-(
    """
    # TODO: should have 1 interface to all PWM: Raspi SW, Raspi HW, and ext. chips e.g. PCA9685
    #       possibly through a factory method.
    def __init__(self, cfg):
        super().__init__(cfg)
        addr = assign_pwm(self._channel, True)  # may raise exceptions InvalidAddr|PortInuse

        if type(addr) is int:
            pin = int(addr)
            self.name = 'PWM %d @ pin %d' % (self._channel, pin)
            if not self._fake:
                GPIO.setup(pin, GPIO.OUT)
                self._pwm = GPIO.PWM(pin, 300)
                self._pwm.start(0)
        elif addr[:5] == '/sys/':
            self._pwm = addr
            self.name = 'PWM %d @ sysfs' % self._channel
            with open(path.join(self._pwm, 'enable'), 'wt') as p:
                p.write('0')
            with open(path.join(self._pwm, 'period'), 'wt') as p:
                p.write('3333333')
        else:
            raise DriverNYI()

        if self._fake:
            self.name = '!' + self.name

        self.write(0)

    def close(self):
        if not self._fake:
            addr = assign_pwm(self._channel, False)
            if type(addr) is str:
                with open(path.join(self._pwm, 'enable'), 'wt') as p:
                    p.write('0')
            else:
                pin = int(addr)
                self._pwm.stop()
                GPIO.cleanup(pin)

    def write(self, val):
        log.info('%s -> %f' % (self.name, float(val)))
        if not self._fake:
            if type(self._pwm) is str:
                with open(path.join(self._pwm, 'duty_cycle'), 'wt') as p:
                    p.write('%d' % int(val / 100.0 * 3333333))
                with open(path.join(self._pwm, 'enable'), 'wt') as p:
                    p.write('1' if val > 0 else '0')
            else:
              self._pwm.ChangeDutyCycle(float(val))
        else:
            self._val = float(val)

"""
class SoftPWM:
    def __init__(self, pin):
    open:   GPIO.setup(pin, GPIO.OUT)
            _pwm = GPIO.PWM(pin, 300)
            _pwm.start(0)
    set:    _pwm.ChangeDutyCycle(perc)
    close:  _pwm.stop()
            GPIO.cleanup(pin)

class SysfsPWM:
    def __init__(self, ch):
    open:   ch -> export
            0 -> duty_cycle
            1 -> enable
            3333333ns -> period
    set:    perc / 1000.0 * period -> duty_cycle
    close:  0 -> enable
            ch -> unexport
"""

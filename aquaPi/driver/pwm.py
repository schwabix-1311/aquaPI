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
        addr = assign_pwm(self._channel, True)  # may raise exceptions InvalidAdr|PortInuse

        if type(addr) is int:
            self.name = 'PWM %d @ pin %d' % (self._channel, addr)
            if not self._fake:
                GPIO.setup(pin, GPIO.OUT)
                self._pwm = GPIO.PWM(pin, 300)
                self._pwm.start(0)
#         elif addr[:5] == '/sys/':
#             self.name = 'PWM %d @ sysfs' % (self._channel, addr)
#             with open(path.join(addr, 'period', 'wt') as p:
#                 p.write('3333333')
#             with open(path.join(addr, 'enable', 'wt') as p:
#                 p.write('0')
        else:
            raise DriverNYI()

        if self._fake:
            self.name = '!' + self.name

        self.write(0)

    def close(self):
        if not self._fake:
            self._pwm.stop()
            pin = assign_pwm(self._channel, False)
            GPIO.cleanup(pin)

    def write(self, val):
        log.info('%s -> %f' % (self.name, float(val)))
        if not self._fake:
            self._pwm.ChangeDutyCycle(float(val))
        else:
            self._val = float(val)
            #with open(path.join(addr, 'enable', 'wt') as p:
            #    p.write('0')
            #with open(path.join(addr, 'duty_cycle', 'wt') as p:
            #    p.write('1')

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

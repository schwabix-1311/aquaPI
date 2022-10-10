#!/usr/bin/env python3

import sys
import logging
import os
from os import path
import math
import time
import random

from .base import *


log = logging.getLogger('Driver 1-wire')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== 1-wire ==========


class DriverDS1820(InDriver):
    # @staticmethod
    # def find():

    def __init__(self, cfg):
        """ 1-wire temperature sensor of Dallas DS1820 series
            Sensor types vary by conversion speed and resolution.
            Paarasitic power is supported; the typical read error of 85°C
            resulting from this (on cheap sensors?) is filtered out before
            an exception is raised,
            cfg = { address : string   # 1-wire bus address, see DriverDS1820.find()
                  , fast: False        # increase precision & switch frequncy (disable moving avaerage)
                  , fake: False        # force driver simulation even on Raspi
                  , fake_inival: 25.0  # start value for the fake driver
                  }
            Fake is always set on non-Raspi.
        """
        super().__init__(cfg)
        self.name = 'DS1820 @ ' + cfg['address']

        self._fast = False
        if 'fast' in cfg:
            self._fast |= bool(cfg['fast'])

        self._fake = not is_raspi()
        if 'fake' in cfg:
            self._fake |= bool(cfg['fake'])

        if not self._fake:
            self._val = 0
            self._err_cnt = 0
            self._err_retry = 3
            # DS1820 family:  /sys/bus/w1/devices/28-............/temperature(25125) ../resolution(12) ../conv_time(750)
            self._sysfs_path = '/sys/bus/w1/devices/%s/' % cfg['address']
            if not path.exists(self._sysfs_path):
                raise Exception('Wrong address, no DS1820 found at ' + self._sysfs_path)
            self._temp = path.join(self._sysfs_path, 'temperature')
            # required? read resolution: _sysfs_path, 'resolution' [bits) e.g. 12
        else:
            self.name = 'fake ' + self.name
            self._initval = 25.0
            if 'fake_initval' in cfg:
                self._initval = float(cfg['fake_initval'])
            self._val = self._initval
            self._dir = 1

    # def __getstate__(self):
    #     super().__getstate__()
    #     return state

    # def __setstate__(self, state):
    #     log.debug('DriverDS1820.setstate %r', state)
    #     self.__init__(state['name'], state['cfg'])

    def read(self):
        if not self._fake:
            with open(self._temp, 'r') as temp:
                ln = temp.readline()
                log.debug('DS1820 read %s' % ln)
                if ln and not ln == '85000\n':
                    val = float(ln) / 1000
                    if self._fast:
                        self._val = val
                    else:
                        self._val = (self._val + val) / 2  # mavg(2)
                    self._err_cnt = 0
                elif self._err_cnt <= self._err_retry:
                    self._err_cnt += 1
                else:
                    log.error('DriverDS1820 read error')
                    raise DriverReadError()
        else:
            rnd = random.random()
            if rnd < .1:
                self._dir = math.copysign(1, self._initval - self._val)  #*= -1
            elif rnd > .7:
                self._val += 0.05 * self._dir
            self._val = round(min(max(self._initval - 1, self._val), self._initval + 1), 2)
        return float(self._val)

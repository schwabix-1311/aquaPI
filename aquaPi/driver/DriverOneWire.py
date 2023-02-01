#!/usr/bin/env python3

import logging
from os import path
import glob
import math
import random

from .base import (InDriver, IoPort, PortFunc, is_raspi, DriverInvalidAddrError, DriverReadError)

log = logging.getLogger('DriverOneWire')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== 1-wire ==========


class DriverDS1820(InDriver):
    @staticmethod
    def find_ports():
        io_ports = {}
        if not is_raspi():
            # name: IoPort('function', 'driver', 'cfg', 'dependants')
            io_ports = {
                'DS1820 xA2E9C': IoPort(PortFunc.Ain, DriverDS1820
                                       , {'adr': '28-0119383a2e9c', 'fake': True}, []),
                'DS1820 x7A71E': IoPort(PortFunc.Ain, DriverDS1820
                                       , {'adr': '28-01193867a71e', 'fake': True}, [])
            }
        else:
            # TODO: GPIO 4 is the Raspi default, allow alternatives!
            deps = ['GPIO 4 in', 'GPIO 4 out']

            for sensor in glob.glob('/sys/bus/w1/devices/28-*'):
                port_name = 'DS1820 x%s' % sensor[-5:].upper()
                io_ports[port_name] = IoPort( PortFunc.Ain,
                                              DriverDS1820,
                                              {'adr': sensor},
                                              deps )
        return io_ports

    def __init__(self, func, cfg):
        """ 1-wire temperature sensor of Dallas DS1820 series
            Sensor types vary by conversion speed and resolution.
            Parasitic power is supported; the typical read error of 85°C
            resulting from this (on cheap sensors?) triggers retrys before
            an exception is raised,
            cfg = { adr : string       # 1-wire bus adr, see DriverDS1820.find()
                  , fake: False        # force driver simulation even on Raspi
                  , fake_initval: 25.0  # start value for the fake driver
                  }
            Fake is always set on non-Raspi.
        """
        super().__init__(func, cfg)
        self.name = 'DS1820 @ ' + cfg['adr']
        if self._fake:
            self.name = '!' + self.name

        if not self._fake:
            self._val = 0
            self._err_cnt = 0
            self._err_retry = 3
            # DS1820 family:  /sys/bus/w1/devices/28-............/temperature(25125) ../resolution(12) ../conv_time(750)
            self._sysfs_adr = cfg['adr']
            if not path.exists(self._sysfs_adr):
                raise DriverInvalidAddrError(adr=self._sysfs_adr)
            self._temp = path.join(self._sysfs_adr, 'temperature')
            if not path.exists(self._temp):
                self._temp = path.join(self._sysfs_adr, 'w1_slave')
            # required? read resolution: _sysfs_adr, 'resolution' [bits) e.g. 12
        else:
            self._initval = 25.0
            if 'fake_initval' in cfg:
                self._initval = float(cfg['fake_initval'])
            self._val = self._initval
            self._dir = 1

    def __del__(self):
        self.close()

    def close(self):
        log.debug('Closing %r', self)
        # pass

    def read(self):
        if not self._fake:
            with open(self._temp, 'r', encoding='ascii') as temp:
                ln = temp.readline()
                if self._temp[-8:] == 'w1_slave':
                    ln = temp.readline()
                    ln = ln[29:]  # e.g. '90 01 4b 46 7f ff 0c 10 33 t=25000'
                log.debug('%s = %s', self.name, ln)
                if ln and not ln == '85000\n':
                    val = float(ln) / 1000
                    self._val = val
                    self._err_cnt = 0
                elif self._err_cnt <= self._err_retry:
                    self._err_cnt += 1
                else:
                    raise DriverReadError(self.name)
        else:
            rnd = random.random()
            if rnd < .1:
                self._dir = math.copysign(1, self._initval - self._val)  # *= -1
            elif rnd > .7:
                self._val += 0.05 * self._dir
            self._val = round(min(max(self._initval - 1, self._val), self._initval + 1), 2)
        log.info('%s = %s', self.name, self._val)
        return float(self._val)

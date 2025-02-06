#!/usr/bin/env python3

import logging
from os import path
import glob

from .base import (AInDriver, IoPort, PortFunc, is_raspi,
                   DriverInvalidAddrError, DriverReadError)

log = logging.getLogger('driver.DriverOneWire')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== 1-wire ==========


class DriverDS1820(AInDriver):
    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        io_ports = {}
        if is_raspi():
            # TODO: GPIO 4 is the Raspi default, auto-detect alternatives!
            deps = ['GPIO 4 in', 'GPIO 4 out']

            for sensor in glob.glob('/sys/bus/w1/devices/28-*'):
                port_name = 'DS1820 x%s' % sensor[-5:].upper()
                io_ports[port_name] = IoPort(PortFunc.Ain,
                                             DriverDS1820,
                                             {'adr': sensor},
                                             deps)
        else:
            # name: IoPort('function', 'driver', 'cfg', 'dependants')
            io_ports = {
                'DS1820 xA2E9C': IoPort(PortFunc.Ain, DriverDS1820,
                                        {'adr': '28-0119383a2e9c', 'fake': True}, []),
                'DS1820 x7A71E': IoPort(PortFunc.Ain, DriverDS1820,
                                        {'adr': '28-01193867a71e', 'fake': True}, [])
            }
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        """ 1-wire temperature sensor of Dallas DS1820 series
            Sensor types vary by conversion speed and resolution.
            Parasitic power is supported; the typical read error of 85°C
            resulting from this (on cheap sensors?) triggers retrys before
            an exception is raised,
            cfg = { adr : string  # 1-wire bus adr, see DriverDS1820.find()
                  , fake: False   # force driver simulation even on Raspi
                  }
            Fake is always set on non-Raspi.
        """
        super().__init__(cfg, func)
        self.name: str = 'DS1820 @ ' + cfg['adr']
        if self._fake:
            self.name = '!' + self.name

        if not self._fake:
            self._val: float = 0
            self._err_cnt: int = 0
            self._err_retry: int = 3
            # DS1820 family:
            # /sys/bus/w1/devices/28-............/temperature(25125)
            #                                  ../resolution(12)
            #                                  ../conv_time(750)
            self._sysfs_adr: str = cfg['adr']
            if not path.exists(self._sysfs_adr):
                raise DriverInvalidAddrError(self._sysfs_adr)
            self._temp: str = path.join(self._sysfs_adr, 'temperature')
            if not path.exists(self._temp):
                self._temp = path.join(self._sysfs_adr, 'w1_slave')
        else:
            self._val = self.initval
            self._dir: int = 1

    def read(self) -> float:
        if self._fake:
            return super().read()

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
                raise DriverReadError()

        log.info('%s = %s', self.name, self._val)
        return float(self._val)

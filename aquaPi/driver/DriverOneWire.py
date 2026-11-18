#!/usr/bin/env python3

import logging
from os import path
import glob

from .base import (AInDriver, IoPort, PortFunc, is_raspi, gpio_deps,
                   DriverInvalidAddrError, DriverReadError)

log = logging.getLogger('driver.DriverOneWire')


# ========== 1-wire ==========


W1_GPIO_DEVICES = '/sys/bus/platform/drivers/w1-gpio/*/of_node/gpios'


def w1_gpio_pins(pattern: str = W1_GPIO_DEVICES) -> list[int]:
    """ GPIO pins of all active w1-gpio buses (dtoverlay=w1-gpio[,gpiopin=N]),
        from their device tree 'gpios' property: big-endian u32 triples
        <controller phandle, pin, flags> - two of them with a pull-up pin.
        Sensors can't be mapped to their own bus (the w1 bus masters in
        sysfs have no link to their platform device), so every 1-Wire
        sensor reserves the pins of all buses - they belong to the w1
        driver anyway. Falls back to the Raspi default GPIO 4.
    """
    pins: set[int] = set()
    for gpios in glob.glob(pattern):
        try:
            with open(gpios, 'rb') as f:
                raw = f.read()
        except OSError as ex:
            log.debug('Cannot read %s: %r', gpios, ex)
            continue
        cells = [int.from_bytes(raw[i:i + 4], 'big') for i in range(0, len(raw) - 3, 4)]
        pins.update(cells[1::3])
    return sorted(pins) or [4]


class DriverDS1820(AInDriver):
    _BUS = 'OneWire'

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        io_ports = {}
        if is_raspi():
            log.info('Scanning OneWire devices ...')

            deps = gpio_deps(*w1_gpio_pins())
            for idx, sensor in enumerate(sorted(glob.glob('/sys/bus/w1/devices/28-*'))):
                io_ports[f'DS1820 #{idx + 1}'] = IoPort(PortFunc.Ain, DriverDS1820,
                                                        {'adr': sensor}, deps)
        else:
            log.info('Faking OneWire devices ...')
            io_ports = {
                'DS1820 #1': IoPort(PortFunc.Ain, DriverDS1820,
                                    {'adr': '28-01193867a71e', 'name': 'DS1820 x7A71E',
                                     'fake': True}, []),
                'DS1820 #2': IoPort(PortFunc.Ain, DriverDS1820,
                                    {'adr': '28-0119383a2e9c', 'name': 'DS1820 xA2E9C',
                                     'fake': True}, [])
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
        self.name = self._mark_fake('DS1820 @ ' + cfg['adr'])
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

    def read(self) -> float:
        if self._fake:
            return super().read()

        with open(self._temp, 'r', encoding='ascii') as temp:
            ln = temp.readline()
            if self._temp.endswith('w1_slave'):
                ln = temp.readline()
                ln = ln[29:]  # e.g. '90 01 4b 46 7f ff 0c 10 33 t=25000'
            log.debug('%s = %s', self.name, ln)
            if ln and ln != '85000\n':
                val = float(ln) / 1000
                self._val = val
                self._err_cnt = 0
            elif self._err_cnt <= self._err_retry:
                self._err_cnt += 1
            else:
                raise DriverReadError()

        log.verbose('%s = %s', self.name, self._val)
        return float(self._val)

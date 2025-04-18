#!/usr/bin/env python3

import logging
import importlib.util
import sys
from os import path
import glob

from .base import (IoPort, PortFunc, Driver,
                   DriverPortInuseError, DriverInvalidPortError, DriverParamError)

log = logging.getLogger('driver')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== global config ==========


driver_config: dict[str, str] = dict()


# ========== IO registry ==========


# IoRegistry is a singleton, access it through a class method IoRegistry.get()
_io_reg: 'IoRegistry'


class IoRegistry(object):
    """
    example

#TODO review this, some is not up to date!

    "GPIO 0..xx in":  { Bin,  DriverGPIO,   {pin: 0..x} }           - unused, func IN, x entries
    "GPIO 0..xx out": { Bout, DriverGPIO,   {pin: 0..x} }           - unused, func IN, x entries
--    "IOext 1..7 in":  { Bin,  DriverPCFxx,  {adr: 0x47, ch: x} }    - unused, x entries

    "GPIO 12 out":    { Bout, DriverGPIO,   {pin: 12} }             - Relays
--    "IOext 0 out":    { Bout, DriverPCFxx,  {adr: 0x47, ch: 0} }    - CO2 Ventil
--    "ShellyPlug1":    { Bout, DriverShelly, {ip: '192..', ch:0} }   - S.Plug - Heizer
--    "H-Bridge 1":     { Bout, DriverMotor,  {pins: (21,22)} }       - Dosierpumpe

    "GPIO 20 in":     { Bin,  DriverGPIO,   {pin: 20} }             - Taster
--    "ShellyTemp1":    { Ain,  DriverShelly, {ip: '192..', ch:2} }   - S.Temp1

    "PWM 0":          { Aout, DriverPWM,    {ch: 0, pin: 18} }      - Licht"
    "PWM 1":          { Aout, DriverPWM,    {ch: 1, pin: 19} }      -
--    "S-PWM 2":        { Aout, DriverGPIO,   {pin: 24} }             - Lüfter"
--    "PWMext 0-15":    { Aout, DriverPA9685, {addr:0x7F, ch:0..} }   -
    "TC420 #1 CH1":   { Aout, DriverTC420,  {device:0, ch:1} }      - Mondlicht
--    "TC420 #1 CH3-5": { Aout, DriverTC420,  {device:0, ch:(3,4,5)}} - RGB Licht
--    "ShellyDim":      { Aout, DriverShelly, {ip: '192..', ch:X} }   - Ambilight

    "DS1820 #1":      { Ain,  DriverDS1820,  {adr:'28-..abcde'} }   - Wassertemperatur"
    "ADC #1 in 3":    { Ain,  DriverADS1115,{adr:0x7E, cnt:1, ch:3} }   - pH Sonde"

    Constructor calls each driver's find_ports() to fill io_registry with io_ports.
    Each io_port is defined by a unique name, a driver class and its cfg dictionary,
    plus a list of dependants by name, if applicable.
    Drivers may support more than one function if they implement all their methods.
    Dict cfg is driver's private property!
    Instantiation of a port/pin driver via driver_factory reserves the io_port, and
    the listed dependants, e.g. PWM may use a std GPIO pin; in this case GPIO pin
    is marked used as long as PWM is in use.
    driver_destruct(key) returns IoPort to unused. List of deps is released unless
    still used by some other port.

    Multi-port drivers (RGB, Motor) may need a dedicated factory method.
    Very likely getting a higher level driver and a tupel of IoPorts.  TBD!
    """

    _map: dict[str, IoPort] = {}

    @classmethod
    def get(cls) -> 'IoRegistry':
        return _io_reg

    def __init__(self):
        # iterate all class imports from a module, then call each class' port enumerator
        # https://stackoverflow.com/questions/7584418/iterate-the-classes-defined-in-a-module-imported-dynamically
        # https://stackoverflow.com/questions/4821104/dynamic-instantiation-from-string-name-of-a-class-in-dynamically-imported-module

        # This may be a hack, although it is documented on python.org for importlib.
        # We load all modules Driver*.py from specific folders, then lookup all
        # descendants of class Driver found in the module dicts.
        # Those with a method find_ports() can report "their" IoPorts to IoRegistry.
        # Maybe there's a much simpler way to achieve the same though.

        # all driver modules are dynamically imported in __init__.py and added to sys.modules
        drv_mod_names = [mod for mod in sys.modules if 'driver.' in mod]
        drv_classes = set()

        # collect them in a set to avoid duplicates
        for name in drv_mod_names:
            drv_module = sys.modules[name]
            log.debug('# module %s', drv_module)
            mod_drivers = {cl for cl in drv_module.__dict__.values()
                            if type(cl) is type and issubclass(cl, Driver)}
            drv_classes |= mod_drivers

        for drv in drv_classes:
            if hasattr(drv, 'find_ports'):
                drv_ports = drv.find_ports()
                log.info('Driver %s reported ports %r', drv.__name__, [k for k in drv_ports])

                # TODO: reject duplicate ports, same port should in theory not be reported
                #      by multiple drivers, but better play safe: len(_map.keys() & drv_ports.keys()) > 0
                IoRegistry._map.update(drv_ports)

        log.brief('Port drivers found for:')
        log.brief('%r', [k for k in sorted(IoRegistry._map)])

    def get_ports_by_function(self, funcs: list[PortFunc], in_use: bool = False
                              ) -> dict[str, IoPort]:
        """ returns a view of free or used IoPorts filtered by iterable funcs.
        """
        mp = IoRegistry._map
        return {key: mp[key] for key in mp
                if mp[key].func in funcs and bool(mp[key].used) == in_use}

    def driver_factory(self, port: str, drv_options: dict | None = None
                       ) -> Driver | None:
        """ Create a driver for a port found in io_ports.keys().
            Drivers that use >1 port are created by a dedicated factory (later)
        """
        log.debug('create a driver for %r', port)
        if port not in IoRegistry._map:
            raise DriverInvalidPortError(port)

        io_port = IoRegistry._map[port]
        if io_port.used:
            raise DriverPortInuseError(port)

        try:
            if drv_options:
                io_port.cfg.update(drv_options)
            driver = io_port.driver(io_port.cfg, io_port.func)
            # same as io_port.used += 1 - on immutable
            IoRegistry._map[port] = io_port._replace(used=io_port.used + 1)

            for dep in io_port.deps:
                # same as IoRegistry._map[dep].used += 1
                dep_port = IoRegistry._map[dep]
                IoRegistry._map[dep] = dep_port._replace(used=dep_port.used + 1)

            return driver
        except Exception:
            log.exception('Failed to create port driver: %s', port)
            raise

    def driver_destruct(self, port: str, driver: Driver) -> None:
        log.debug('destruct driver for %r', port)
        if port not in IoRegistry._map:
            raise DriverInvalidPortError(port)

        io_port = IoRegistry._map[port]
        driver.close()
        # same as io_port.used = 0
        IoRegistry._map[port] = io_port._replace(used=0)

        for dep in io_port.deps:
            # same as IoRegistry._map[dep].used -= 1
            dep_port = IoRegistry._map[dep]
            IoRegistry._map[dep] = dep_port._replace(used=dep_port.used - 1)


# ========== IoRegistry is a singleton -> 1 global instance ==========



# flake8: noqa
from .base import *  # noqa: F403 allow import * for the runtime-imports


def create_io_registry():
    """ Create the singleton _io_registry, which is accessible as
        IoRegistry.get()
    """
    # pylint: disable-next=W0603
    global _io_reg

    DRIVER_FILE_PREFIX = 'Driver'
    CUSTOM_DRIVERS = 'CustomDrivers'

    # import all files named Driver*.py into our package,
    #  including from subfolder CustomDrivers
    __path__.append(path.join(__path__[0], CUSTOM_DRIVERS))

    for drv_path in __path__:
        for drv_file in glob.glob(path.join(drv_path, DRIVER_FILE_PREFIX + '*.py')):
            log.info('Found driver file %s', drv_file)

            drv_name = path.basename(drv_file)
            if drv_name.startswith(DRIVER_FILE_PREFIX):
                drv_name = drv_name[len(DRIVER_FILE_PREFIX):]
            if drv_name.endswith('.py'):
                drv_name = drv_name[:-3]
            drv_name = __name__ + '.' + drv_name.lower()
            drv_spec = importlib.util.spec_from_file_location(drv_name, drv_file)
            #log.debug('Driver spec %s', drv_spec)

            if drv_spec:
                drv_mod = importlib.util.module_from_spec(drv_spec)
                log.debug('Driver module %s', drv_mod)

                sys.modules[drv_name] = drv_mod
                if drv_spec.loader:
                    drv_spec.loader.exec_module(drv_mod)
                    log.debug('  loaded module %s', drv_mod)

    _io_reg = IoRegistry()

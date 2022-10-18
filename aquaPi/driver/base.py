#!/usr/bin/env python3

import logging
import sys
from os import path
from enum import Enum
from collections import namedtuple
try:
    import RPi.GPIO as GPIO
except:
    pass


log = logging.getLogger('Driver Base')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
log.setLevel(logging.INFO)
log.setLevel(logging.DEBUG)


# ========== common functions ==========


def is_raspi():
    model = ''
    if path.exists('/sys/firmware/devicetree/base/model'):
        with open('/sys/firmware/devicetree/base/model', 'r') as f:
            model = f.readline()
    return 'raspberry' in model.lower()


# ========== Exceptions ==========


class DriverNYI(Exception):
    def __init__(self, msg='Not yet implemented.'):
        super().__init__(msg)

class DriverParamError(Exception):
    def __init__(self, msg='Invalid parameter value.'):
        super().__init__(msg)

class DriverInvalidAddrError(Exception):
    def __init__(self, msg=None, adr=None):
        if not msg:
            msg = 'Pin, channel or address %r does not exist.' % adr
        super().__init__(msg)

class DriverPortInuseError(Exception):
    def __init__(self, msg=None, port=None):
        if not msg:
            msg = 'Pin or channel %r is already assigned.' % port
        super().__init__(msg)

class DriverReadError(Exception):
    def __init__(self, msg='Failed to read a valid value.'):
        super().__init__(msg)

class DriverWriteError(Exception):
    def __init__(self, msg='Failed to write value to the output.'):
        super().__init__(msg)


# ========== base classes ==========


class Driver:
    """ base class of all drivers
        Drivers persist their cinfiguration in dict 'cfg', no need for
        __getstate__/__setstate__ overloads in derived classes.
    """
    # TODO this persistance approach could be transferred to MsgNodes!
    def __init__(self, func, cfg):
        self.name = '!abstract'
        self.func = None
        self.cfg = cfg
        self._fake = not is_raspi()
        if 'fake' in cfg:
            self._fake |= bool(cfg['fake'])

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.cfg)


class InDriver(Driver):
    """ base class of all input drivers
        InDriver can be read, e.g. a temperature sensor.
    """
    def __init__(self, func, cfg):
        super().__init__(func, cfg)
        self.name = '!abstract IN'
        self._interval = 0

    def read(self):
        return 0.0


class OutDriver(Driver):
    """ base of all output drivers
        OutDriver can be written, the last written value can be read.
    """
    def __init__(self, func, cfg):
        super().__init__(func, cfg)
        self.name = '!abstract OUT'
        self._state = 0

    def write(self, state):
        self._state = state

    def read(self):
        return self._state


# ========== IO resource map ==========


"""
example

"GPIO 0..xx": { IO,  DriverGPIO,   {pin: 0..x} }         - unused, func IO -> OUT/IN, x entries
"IOext 1..7": { IO,  DriverPCFxx,  {addr: 0x47, ch: x} } - unused, x entries

"GPIO 12":    { OUT, DriverGPIO,   {pin: 12} }           - Relais
"IOext 0":    { OUT, DriverPCFxx,  {addr: 0x47, ch: 0} } - CO2 Ventil
"ShellyPlug1":{ OUT, DriverShelly, {ip: '192..', ch:0} } - S.Plug - Heizer
"H-Bridge 1": { OUT, Drivermotor,  {pins: (21,22)} }     - Dosierpumpe

"GPIO 20":    { IN,  DriverGPIO,   {pin: 20} }           - Taster
"ShellyTemp1":{ IN,  DriverShelly, {ip: '192..', ch:2} } - S.Temp1

"PWM 0":      { PWM, DriverPWM,    {ch: 0, pin: 18} }    - Licht"
"PWM 1":      { PWM, DriverPWM,    {ch: 1, pin: 19} }    -
"S-PWM 2":    { IO/PWM, DriverGPIO, {pin: 24} }          - Lüfter"   GPIO conflict!
"PWMext 0-15":{ PWM, DriverPA9685, {addr:0x7F, ch:0..} } -
"TC420 1":    { PWM, DriverTC420,  {usb:id, ch:1} }      - Mondlicht
"TC420 2":    { PWM, DriverTC420,  {usb:id, ch:(3,4,5)}} - RGB Licht
"ShellyDim":  { PWM, DriverShelly, {ip: '192..', ch:X} } - Ambilight

"Sens 1":     { ADC, DriverOneWr,  {id:'28-xx'} }        - Wassertemperatur"
"ADC 3":      { ADC, DriverAD1115, {addr:0x7E, ch:3} }   - pH Sonde"

Initial enumeration fills this map via static driver functions.
GPIO has 3 functions: IO (=undetermined), IN, OUT. or 4th: S-PWM?
Drivers can provide entries for more than one function if they implement all their methods.
Each channel/port/pin is one entry. Dict cfg is driver's private property!
Creation of a driver instance reserves the entry, in case of GPIO (or soft-PWM) this may change function!
get_ports_by_function() returns a view on avialbale or used IoPorts.
driver_factory(key,func) creates a driver for specified port and function.
driver_destruct(key) returns IoPort to unused. This must restore initial function.

Multi-port drivers (RGB, motor) will need a dedicated factory method; very likely getting a higher level driver and a tupel of IoPorts.
"""

IoPort = namedtuple('IoPort', ['function', 'driver', 'cfg'])

class PortFunc(Enum):
    IO, IN, OUT, PWM, ADC = range(1, 6)

class PinFunc(Enum):
    UNKNOWN = -1
    OUT = 0
    IN = 1
    SERIAL = 40
    SPI = 41
    I2C = 42
    PWM = 43


class IoRegistry(object):
    _map = {}
    _inuse = {}

    def __init__(self):
        # iterate all class imports from a module, then call each class' port enumerator
        # https://stackoverflow.com/questions/7584418/iterate-the-classes-defined-in-a-module-imported-dynamically
        # https://stackoverflow.com/questions/4821104/dynamic-instantiation-from-string-name-of-a-class-in-dynamically-imported-module

        # This may be a hack, although it is documented on python.org for importlib.
        # We load all modules Driver*.py in specific folders, then lookup all
        # descendants of class Driver found in the module dicts.
        # Those with a method find_ports() can report "their" IoPorts to IoRegistry.
        # May be there's a much simpler ways to achieve the same though.

        # all driver modules are dynamically imported in __init__.py and added to sys.modules
        drv_mod_names = [mod for mod in sys.modules if 'driver.' in mod]
        drv_classes = set()

        # collect them in a set to avoid duplicates
        for name in drv_mod_names:
            drv_module = sys.modules[name]
            log.debug('# module %s', drv_module)
            dict_classes = [cl for cl in drv_module.__dict__.values() if type(cl) is type]
            for mod_cl in dict_classes:
                if issubclass(mod_cl, Driver):
                    log.debug('found drv class %r', mod_cl)
                    drv_classes.add(mod_cl)

        for drv in drv_classes:
            if hasattr(drv, 'find_ports'):
                drv_ports = drv.find_ports()
                log.debug('driver %r reported %r', drv, drv_ports)
                # TODO should reject duplicate ports, same port should in theory not be reported
                #      by multiple drivers, but better play safe
                IoRegistry._map.update(drv_ports)
        print('%r', IoRegistry._map)

    def get_ports_by_function(self, funcs, free=True):
        mp = IoRegistry._map if free else IoRegistry._inuse
        # return [key for key in mp if mp[key].function in funcs]
        return {key: mp[key] for key in mp if mp[key].function in funcs}

    def driver_factory(self, port, func):
        """ Create a driver for a single port.
            Parameter func requests the function for ports that support alternatives, e.g. IO -> In or OUT
            Drivers that use >1 port are created by a dedicated factory (later)
        """
        log.debug('create a driver for %r - %r', port, func)
        if port in IoRegistry._inuse.keys():
            raise DriverPortInuseError(port=port)
        if port not in IoRegistry._map.keys():
            raise DriverParamError('There is no port named %s' % port)

        try:
            io_port = IoRegistry._map[port]
            driver = io_port.driver(func, io_port.cfg)

            IoRegistry._inuse.update(port = IoPort(func, io_port.driver, io_port.cfg))
            del IoRegistry._map[port]
        except Exception as ex:
            #TODO report error, e.g.
            log.exception('Failed to create driver:' + port)
        return driver

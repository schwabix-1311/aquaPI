#!/usr/bin/env python3

import logging
from os import path
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


# ========== IO resource map ==========


"""
[ (driver,   addr,        port,    func, free) ]

('GPIO',    '',           12,       OUT, False )   "GPIOout 12 - Relais"
('GPIO',    '',           0/1/4-17, IO,  True )
('Motor',   '',           (21,22),  OUT, False )   "H-Bridge - Dosierpumpe"
('I2C',     'x47',        0,        OUT, False )   "IOext 0 - CO2 Ventil"
('I2C',     'x47',        1-7,      IO,  True )    "IOext 0 - CO2 Ventil"
('Shelly',  '192.16..',   0,        OUT, False )   "Shelly Plug - Heizer"

('GPIO',    '',           20,       IN,  False )   "GPIOin 20 - Taster"
('Shelly',  '192.16..',   1,        IN,  False )   "Shelly Temp.1"

('PWM',     '/sys/...',   18,       PWM, False )   "H-PWM 0 - Licht"
('PWM',     '/sys/...',   19,       PWM, True )    "H-PWM 1"
('PWM',     '',           24,       PWM, True )    "S-PWM 2 - Lüfter"
('PA9685',  'x7F',        15,       PWM, True )    "X-PWM 3"
('TC420',   '??',         (3,4,5),  PWM, False )   "TC420 2 - RGB Licht"
('Shelly',  '192.16..',   0,        PWM, False )   "Shelly Dimmer - Ambilight"

('AD1115',  'x7E',        2,        ADC, True )    "ADC 3 - pH Sonde"
('OneWire', '28-xx',      0,        ADC, False )   "Sens 1 - Wassertemperatur"

Initial enumeration fills this map via static driver functions. 
GPIO has 3 functions: undetermined IO, IN, OUT
Drivers can provide entries for more than one function if they implement all their methods.
Each channel/port/pin is one entry. We will need multi-channel drivers (RGB, motor).
Creation of a driver instance reserves the entry, in case of GPIO (or soft-PWM) this may change function!
Function to query avilable entries by function. 
Function to allocte/release a set of entries. This must restore initial function.

IoPort = namedtupel('IoPort', ['function', 'driver', 'address', 'port', 'free'])

class IoManager(object):
    _map = {}

    def __init__(self):
        # iterate all class imports from a module, then call each class' port enumerator
        # https://stackoverflow.com/questions/7584418/iterate-the-classes-defined-in-a-module-imported-dynamically
        for driver in ['DrvGPIO', 'OneWire']):
            _map.update(driver.enumerate(...))
"""


_pins_available = None
_pins_unused = None

# index into this array is channel num
# entries are  int - GPIO pin for Soft PWM
#              '/sys/...' - sysfs path to Hard PWM
# (future)     'pca9685@adr#1' - chip, I2C adr & channel
_pwms_available = None
_pwms_unused = None

_pin_func_map = {-1: 'UNKNOWN', 0: 'OUT', 1: 'IN', 40: 'SERIAL', 41: 'SPI', 42: 'I2C', 43: 'PWM'}

def _init_maps():
    global _pins_available, _pins_unused
    global _pwms_available, _pwms_unused

    if not _pins_available:
        if is_raspi():
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            _pins_available = set()
            _pwms_available = []
            pwm_cnt = 0
            for i in range(28):
                try:
                    fnc = GPIO.gpio_function(i)
                    if fnc in [0, 1]:
                        _pins_available.add(i)
                    elif fnc == 43:
                        _pwms_available.append('/sys/class/pwm/pwmchip0/pwm%d/' % pwm_cnt)
                        #soft-PWM _pwms_available.append(i)
                        pwm_cnt += 1
                    else:
                        log.info('pin %d is in use as %s' % (i, _pin_func_map[fnc]))
                except:
                    log.debug('func pin %d = %d' % (i, fnc))
        else:
            # not a Raspi, simulate typical IO layout, skip I²C and PWM
            _pins_available = {0, 1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 25, 26, 27}
            _pwms_available = [18, 19]

        log.brief('available GPIO pins: %r' % _pins_available)
        log.brief('available PWM channels: %r' % _pwms_available)
        _pins_unused = set(_pins_available)
        _pwms_unused = set(range(len(_pwms_available)))


def get_unused_pins():
    _init_maps()
    return _pins_unused


def assign_pin(pin, used):
    global _pins_available, _pins_unused

    _init_maps()
    # pin must be a member of set _pins_available
    if not pin in _pins_available:
        raise DriverInvalidPortError(port=pin)
    if used and not pin in _pins_unused:
        raise DriverPortInuseError(port=pin)

    if used:
        _pins_unused.remove(pin)
    else:
        _pins_unused.add(pin)


def get_unused_pwms():
    _init_maps()
    return _pwms_unused


def assign_pwm(channel, used):
    global _pwms_available, _pwms_unused

    _init_maps()
    # channel must be an index into array pwms_available
    if channel < 0 or channel >= len(_pwms_available):
        raise DriverInvalidAddrError(adr=channel)
    if used and not channel in _pwms_unused:
        raise DriverPortInuseError(port=channel)

    if used:
        _pwms_unused.remove(channel)
    else:
        _pwms_unused.add(channel)
    return _pwms_available[channel]


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
    def __init__(self, cfg):
        self.name = '!abstract'
        self.cfg = cfg
        self._fake = not is_raspi()
        if 'fake' in cfg:
            self._fake |= bool(cfg['fake'])

    def __getstate__(self):
        state = {'name': self.name, 'cfg': self.cfg}
        log.debug('Driver.getstate %r', state)
        return state

    def __setstate__(self, state):
        log.debug('Driver.setstate %r', state)
        self.__init__(state['cfg'])
        self.name = state['name']

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.cfg)


class InDriver(Driver):
    """ base class of all input drivers
        InDriver can be read, e.g. a temperature sensor.
    """
    def __init__(self, cfg):
        super().__init__(cfg)
        self.name = '!abstract IN'
        self._interval = 0

    def read(self):
        return 0.0


class OutDriver(Driver):
    """ base of all output drivers
        OutDriver can be written, the last written value can be read.
    """
    def __init__(self, cfg):
        super().__init__(cfg)
        self.name = '!abstract OUT'
        self._state = 0

    def write(self, state):
        self._state = state

    def read(self):
        return self._state

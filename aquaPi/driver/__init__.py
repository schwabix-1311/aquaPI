#!/usr/bin/env python3

import logging
import importlib.util
import sys
import time
from os import path
import glob

from .base import (IoPort, PortFunc, Driver,
                   DriverPortInuseError, DriverInvalidPortError, DriverParamError)

log = logging.getLogger('driver')


# ========== global config ==========


driver_config: dict[str, str] = dict()


# ========== IO registry ==========


# IoRegistry is a singleton, access it through a class method IoRegistry.get()
_io_reg: 'IoRegistry'


# ========== claim/release rules, shared by the real IoRegistry and by
#             PortClaimPreview's disconnected simulation of it ==========


def _check_claim(m: dict[str, IoPort], claims: dict[str, int], port: str) -> None:
    """ raise if claiming `port` in map `m` (with primary-claim counts
        `claims`) would be illegal - no mutation. Same rule
        driver_factory() enforces on the real registry.
    """
    if port not in m:
        raise DriverInvalidPortError(port)
    io_port = m[port]
    if io_port.used and not io_port.shareable:
        raise DriverPortInuseError(port)
    # a dep already held as somebody's primary means this port's pin is
    # really taken (e.g. 'GPIO 19 out' claimed directly, now 'PWM 1'
    # wants it as a dep) - .used on the primary alone wouldn't catch
    # that ordering. Two primaries sharing a dep only as a dep (a bus)
    # is fine and not recorded in `claims`.
    for dep in io_port.deps:
        dep_port = m.get(dep)
        if claims.get(dep) and dep_port is not None and not dep_port.shareable:
            raise DriverPortInuseError(dep)


def _commit_claim(m: dict[str, IoPort], claims: dict[str, int], port: str) -> None:
    """ mutate `m`/`claims` to record a (pre-checked) claim on `port`. """
    io_port = m[port]
    # same as io_port.used += 1 - on immutable
    m[port] = io_port._replace(used=io_port.used + 1)
    claims[port] = claims.get(port, 0) + 1
    for dep in io_port.deps:
        # same as m[dep].used += 1
        dep_port = m[dep]
        m[dep] = dep_port._replace(used=dep_port.used + 1)


def _commit_release(m: dict[str, IoPort], claims: dict[str, int], port: str) -> None:
    """ mutate `m`/`claims` to release one claim on `port`. """
    io_port = m[port]
    # decrement rather than reset to 0: a shareable port can have more
    # than one concurrent claim, and releasing one must not drop the
    # others' - for a non-shareable port used is always 1 here, so this
    # is equivalent to the old reset-to-0
    m[port] = io_port._replace(used=max(0, io_port.used - 1))
    left = claims.get(port, 0) - 1
    if left > 0:
        claims[port] = left
    else:
        claims.pop(port, None)
    for dep in io_port.deps:
        # same as m[dep].used -= 1
        dep_port = m[dep]
        m[dep] = dep_port._replace(used=dep_port.used - 1)


def _is_free(m: dict[str, IoPort], claims: dict[str, int], port: str) -> bool:
    """ is `port` claimable right now - a shareable port always has room
        for another claim, so it counts as free regardless of its
        current claim count; a port whose dep is somebody's primary (a
        dual-use pin) is not actually claimable even though its own
        .used is still 0.
    """
    io_port = m.get(port)
    if io_port is None:
        return False
    if io_port.shareable:
        return True
    if io_port.used:
        return False
    return not any(claims.get(dep) for dep in io_port.deps)


class PortClaimPreview:
    """ disconnected simulation of IoRegistry's claim/release rules,
        seeded from a snapshot of the live state. Never touches the
        real IoRegistry - used to answer "what would be free / would
        this claim be legal if these releases+claims happened" without
        side effects, e.g. for /wiring's atomic-diff validation
        (aquaPi.db.apply_config_diff). Obtain one via IoRegistry.preview().

        NOT a lock or a transaction, and not thread-safe: `preview()`
        takes a snapshot at one instant; nothing stops the real registry
        from changing (another request's apply_config_diff, or a
        background thread claiming a shareable port, e.g. an Alert's
        escalation send on 'Email #N'/'Telegram #N' from a sensor-reader
        thread - see machineroom/alert_nodes.py) between that snapshot
        and the real apply phase that follows a successful validation.
        A stale preview can only make the real apply phase's own
        (uncommon) DriverPortInuseError surface where it always could -
        this doesn't weaken the existing "validate first" guarantee, it
        just doesn't add locking that was never there either. Real
        `driver_factory`/`driver_destruct` mutate `IoRegistry._map`/
        `_primary_claims` (a plain dict, no lock) the same way - a
        genuine data race between two threads is possible in principle;
        aquaPi has gotten away without one because `flask run` (./run,
        ./dbg) defaults to single-threaded request handling and the only
        cross-thread claim/release traffic is the shareable, exemption-
        heavy Email/Telegram path above. Worth real locking (a
        threading.Lock around _check_claim/_commit_claim/_commit_release,
        or making preview()+apply one held section) if that ever changes
        (multi-threaded/multi-worker serving, more background claim
        traffic) - not done here, flagged 2026-09-14.
    """

    def __init__(self, m: dict[str, IoPort], claims: dict[str, int]):
        self._map = m
        self._claims = claims

    def release(self, port: str) -> None:
        """ no-op for an empty/unknown port - callers pass a node's
            possibly-empty .port straight through """
        if port and port in self._map:
            _commit_release(self._map, self._claims, port)

    def claim(self, port: str) -> None:
        """ raises DriverInvalidPortError/DriverPortInuseError if
            illegal, otherwise records the claim """
        _check_claim(self._map, self._claims, port)
        _commit_claim(self._map, self._claims, port)

    def is_free(self, port: str) -> bool:
        return _is_free(self._map, self._claims, port)


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
    # names currently held *as a primary port* (name -> claim count). A
    # dep bumps the target's .used but is NOT recorded here - that is how
    # a shared bus (several DS1820 on one 1-Wire pin, several ADC channels
    # on one I2C bus) stays allowed while a dual-use pin ('PWM 1' owns
    # 'GPIO 19 out') is not: claiming a port is refused when one of its
    # deps is somebody else's primary.
    _primary_claims: dict[str, int] = {}

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
                # config.json's 'DRIVER_BLACKLIST' (a list of driver class
                # names, e.g. ["DriverShellyRelay"]), handed down via
                # driver_config same as Email/Telegram settings - lets a
                # deployment skip a driver's find_ports() entirely, e.g.
                # for hardware that isn't present or a discovery that's
                # slow/unreliable on that network
                if drv.__name__ in driver_config.get('DRIVER_BLACKLIST', []):
                    log.info('Driver %s is blacklisted, skipping port discovery',
                             drv.__name__)
                    continue

                # log before calling find_ports(), not just after - some
                # drivers do real network I/O here (mDNS/broadcast
                # discovery) that can take several seconds, and a silent
                # multi-second gap in the startup log is easy to mistake
                # for a hung/still-starting process instead of a slow
                # but healthy scan
                log.info('Discovering %s devices/ports for %s ...',
                         getattr(drv, '_BUS', '?'), drv.__name__)
                t_start = time.time()

                # Step 25: a single driver failing to enumerate its ports
                # (e.g. Email/Telegram find_ports() raising DriverConfigError
                # on a misconfigured account, or any other connection issue
                # beyond the internet-outage case they already handle
                # themselves) must not block the whole app from starting -
                # log it and just skip that driver's ports instead.
                try:
                    drv_ports = drv.find_ports()
                except Exception:
                    log.exception('Driver %s failed to report its ports, '
                                  'skipping it', drv.__name__)
                    continue
                log.verbose('Driver %s reported ports %r (%.1fs)',
                         drv.__name__, [k for k in drv_ports], time.time() - t_start)

                dupes = IoRegistry._map.keys() & drv_ports.keys()
                if dupes:
                    log.error('Driver %s reported port(s) %r already claimed '
                              'by another driver, ignoring the duplicate(s)',
                              drv.__name__, sorted(dupes))
                    drv_ports = {k: v for k, v in drv_ports.items() if k not in dupes}
                IoRegistry._map.update(drv_ports)

        log.info('Port drivers found for:')
        log.info('%r', [k for k in sorted(IoRegistry._map)])

    def get_ports_by_function(self, funcs: list[PortFunc], in_use: bool = False
                              ) -> dict[str, IoPort]:
        """ returns a view of free or used IoPorts filtered by iterable funcs.
            A shareable port always has room for another claim, so it
            counts as free regardless of its current claim count.
        """
        mp = IoRegistry._map

        def _free(key: str) -> bool:
            return _is_free(mp, IoRegistry._primary_claims, key)

        return {key: mp[key] for key in mp
                if mp[key].func in funcs
                and (not _free(key) if in_use else _free(key))}

    def preview(self) -> PortClaimPreview:
        """ a disconnected snapshot of the current claim state - see
            PortClaimPreview. A shallow copy suffices: IoPort is an
            immutable namedtuple, every mutation already goes through
            _replace() rather than in place.
        """
        return PortClaimPreview(dict(IoRegistry._map),
                                dict(IoRegistry._primary_claims))

    def driver_factory(self, port: str, drv_options: dict | None = None
                       ) -> Driver | None:
        """ Create a driver for a port found in io_ports.keys().
            Drivers that use >1 port are created by a dedicated factory (later)
        """
        log.debug('create a driver for %r', port)
        _check_claim(IoRegistry._map, IoRegistry._primary_claims, port)
        io_port = IoRegistry._map[port]

        try:
            if drv_options:
                io_port.cfg.update(drv_options)
            driver = io_port.driver(io_port.cfg, io_port.func)
            _commit_claim(IoRegistry._map, IoRegistry._primary_claims, port)
            return driver
        except Exception:
            log.exception('Failed to create port driver: %s', port)
            raise

    def driver_destruct(self, port: str, driver: Driver) -> None:
        log.debug('destruct driver for %r', port)
        if port not in IoRegistry._map:
            raise DriverInvalidPortError(port)

        driver.close()
        _commit_release(IoRegistry._map, IoRegistry._primary_claims, port)


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
            log.verbose('Found driver file %s', drv_file)

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

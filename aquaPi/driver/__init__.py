#!/usr/bin/env python3

import logging
import importlib
import sys
import time
from typing import Any
from os import path
import glob

# re-export the public driver API (see base.__all__), so callers can use
# `from aquaPi.driver import OutDriver, PortFunc, ...`
from .base import *  # noqa: F401,F403
from .base import (IoPort, PortFunc, Driver,
                   DriverPortInuseError, DriverInvalidPortError)

log = logging.getLogger('driver')


# ========== global config ==========


driver_config: dict[str, Any] = {}


# ========== IO registry ==========


# IoRegistry is a singleton, access it through a class method IoRegistry.get()
_io_reg: 'IoRegistry'


# ========== driver modules ==========


DRIVER_FILE_PREFIX = 'Driver'

# CustomDrivers/ goes first in the package search path: a Driver*.py there
# replaces the built-in driver module of the same name - for every import
# of it, also the ones before create_io_registry() (e.g. api.py)
_CUSTOM_PATH = path.join(path.dirname(path.abspath(__file__)), 'CustomDrivers')
if _CUSTOM_PATH not in __path__:
    __path__.insert(0, _CUSTOM_PATH)


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
        traffic).
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


class IoRegistry:
    """ registry of all IoPorts reported by the drivers' find_ports(),
        keyed by a unique, human readable port name, e.g.
            'GPIO 12 out'        Bout  DriverGPIO     {pin: 12}
            'PWM 0'              Aout  DriverPWM      {pin: 18, channel: 0}
            'PCA9685 #1 CH0 PWM' Aout  DriverPCA9685  {adr: 0x40, cnt: 1, ch: 0}
            'DS1820 #1'          Ain   DriverDS1820   {adr: '28-..'}
            'ADC #1 in 3'        Ain   DriverADS1115  {adr: 0x48, cnt: 1, in: 3}
            'Email #1'           Tout  DriverEmail    {...}, shareable

        IoPort.cfg is private to the port's driver class. IoPort.deps
        lists further ports that are claimed along with it, e.g. 'PWM 0'
        occupies 'GPIO 18 in'/'GPIO 18 out'.
        driver_factory(port) instantiates the driver and claims the port
        plus its deps, driver_destruct(port, driver) releases them again.
        A singleton: create it with create_io_registry(), access it with
        IoRegistry.get().
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
        for drv in self._driver_classes():
            if not hasattr(drv, 'find_ports'):
                continue
            # config.json's 'DRIVER_BLACKLIST' (a list of driver class
            # names, e.g. ["DriverShellyRelay"]) lets a deployment skip a
            # driver's discovery entirely, e.g. for hardware that isn't
            # present or a discovery that's slow/unreliable on that network
            if drv.__name__ in driver_config.get('DRIVER_BLACKLIST', []):
                log.info('Driver %s is blacklisted, skipping port discovery',
                         drv.__name__)
                continue
            IoRegistry._add_ports(drv, self._discover(drv))

        log.info('Port drivers found for:')
        log.info('%r', sorted(IoRegistry._map))

    @staticmethod
    def _driver_classes() -> set[type[Driver]]:
        """ all Driver subclasses of the driver modules, which
            create_io_registry() imported into sys.modules. A set, since
            a class imported by several modules shows up more than once.
        """
        drv_classes: set[type[Driver]] = set()
        for name in [mod for mod in sys.modules if 'driver.' in mod]:
            drv_module = sys.modules[name]
            log.debug('# module %s', drv_module)
            drv_classes |= {cl for cl in drv_module.__dict__.values()
                            if type(cl) is type and issubclass(cl, Driver)}
        return drv_classes

    @staticmethod
    def _discover(drv: type[Driver]) -> dict[str, IoPort]:
        """ call drv.find_ports(); a driver failing to enumerate its ports
            (e.g. Email/Telegram raising DriverConfigError on a
            misconfigured account) must not block the app from starting,
            it just contributes no ports.
        """
        # log before calling find_ports(), not just after - some drivers
        # do real network I/O here (mDNS discovery) that can take
        # several seconds, and a silent gap in the startup log is easy to
        # mistake for a hung process
        log.info('Discovering %s devices/ports for %s ...', drv._BUS, drv.__name__)
        t_start = time.time()
        try:
            drv_ports = drv.find_ports()  # type: ignore[attr-defined]
        except Exception:
            log.exception('Driver %s failed to report its ports, skipping it',
                          drv.__name__)
            return {}
        log.verbose('Driver %s reported ports %r (%.1fs)',
                    drv.__name__, list(drv_ports), time.time() - t_start)
        return drv_ports

    @staticmethod
    def _add_ports(drv: type[Driver], drv_ports: dict[str, IoPort]) -> None:
        dupes = IoRegistry._map.keys() & drv_ports.keys()
        if dupes:
            log.error('Driver %s reported port(s) %r already claimed '
                      'by another driver, ignoring the duplicate(s)',
                      drv.__name__, sorted(dupes))
            drv_ports = {k: v for k, v in drv_ports.items() if k not in dupes}
        IoRegistry._map.update(drv_ports)

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


def create_io_registry():
    """ Create the singleton _io_registry, which is accessible as
        IoRegistry.get(). Idempotent: a second call is a no-op.

        The set of drivers/ports doesn't change within a process's
        lifetime, but some drivers do slow I/O in find_ports() (e.g.
        DriverShelly's mDNS scan, ~3s), and MachineRoom.__init__ calls
        this on every construction - e.g. once per test.
    """
    # pylint: disable-next=W0603
    global _io_reg

    if '_io_reg' in globals():
        return

    # import every Driver*.py of the package. A plain import resolves
    # through __path__, where CustomDrivers/ comes first - a custom
    # driver file replaces the built-in one of the same name.
    drv_names = sorted({path.basename(f).removesuffix('.py')
                        for drv_path in __path__
                        for f in glob.glob(path.join(drv_path, DRIVER_FILE_PREFIX + '*.py'))})
    for drv_name in drv_names:
        drv_mod = importlib.import_module(f'{__name__}.{drv_name}')
        if path.dirname(drv_mod.__file__ or '') == _CUSTOM_PATH:
            log.info('Using custom driver %s', drv_mod.__file__)
        log.debug('Loaded driver module %s', drv_mod)

    _io_reg = IoRegistry()

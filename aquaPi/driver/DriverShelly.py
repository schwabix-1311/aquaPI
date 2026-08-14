#!/usr/bin/env python3

import logging
import threading
import time
import requests

try:
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener  # type: ignore[import-untyped]
except ImportError:
    Zeroconf = None
    ServiceBrowser = None
    ServiceListener = object

from .base import (OutDriver, IoPort, PortFunc)


log = logging.getLogger('driver.DriverShelly')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== Shelly relays (Gen1 + Gen2/Gen3, local HTTP API) ==========


DISCOVER_TIMEOUT = 1.5  # mDNS ServiceBrowser window, see _local/shelly_api.md
DISCOVER_PASSES = 2     # independent scans, unioned - see _find_ips()
HTTP_TIMEOUT = 5
MAX_RELAY_CHANNELS = 8  # probing cap, see _identify()
MAX_LIGHT_CHANNELS = 4  # probing cap, see _identify()


class _Listener(ServiceListener):
    def __init__(self) -> None:
        self.ips: set[str] = set()

    def add_service(self, zc, type_, name) -> None:
        if 'shelly' not in name.lower():
            return
        info = zc.get_service_info(type_, name)
        if info:
            self.ips.update(info.parsed_addresses())

    def update_service(self, zc, type_, name) -> None:
        pass

    def remove_service(self, zc, type_, name) -> None:
        pass


def _scan_once(timeout: float) -> set[str]:
    zc = Zeroconf()
    listener = _Listener()
    try:
        ServiceBrowser(zc, ['_shelly._tcp.local.', '_http._tcp.local.'], listener)
        time.sleep(timeout)
    finally:
        zc.close()
    return listener.ips


def _find_ips() -> set[str]:
    """ mDNS broadcast for Shelly devices - Gen2/Gen3 advertise
        '_shelly._tcp.local.' natively; Gen1 devices don't, but show up
        under the generic '_http._tcp.local.' too, filtered by a
        'shelly'-prefixed service name above. 1.5s is a measured-safe
        window (0.5s occasionally missed a device, 1.0s+ was reliable
        in most trials against a real 10-device LAN) - see
        _local/shelly_api.md.

        mDNS is UDP, so a lost query/reply packet can still make a
        single scan under-report even at a reliable window size (one
        such miss was observed live during this driver's development).
        Run DISCOVER_PASSES independent scans and union their results -
        each pass starts a fresh Zeroconf/ServiceBrowser, which actively
        resends the mDNS query, rather than just waiting longer on one
        instance for its own, less frequent internal re-query. A device
        found on any pass counts; a graceful loss of one device on one
        boot must not silently drop its saved node (see db.py's
        load_topology(), which already isolates a missing-port node's
        failure to that one node and tries to notify the user rather
        than crash the whole bus - this is about not needlessly
        triggering that path from a UDP fluke, not about that fault-
        isolation logic itself).
    """
    if not Zeroconf:
        return set()

    ips: set[str] = set()
    for _ in range(DISCOVER_PASSES):
        ips |= _scan_once(DISCOVER_TIMEOUT)
    return ips


def _identify(ip: str) -> dict | None:
    """ probe one IP: identify via /shelly (works on both generations,
        no auth needed even when enabled), get its custom name (free
        on Gen2+ via /shelly's own 'name' field; Gen1 needs a separate
        /settings call, since Gen1 exposes neither a 'gen' nor a
        'name' key via /shelly), then count relay/light channels by
        probing /relay/0.. and /light/0.. until a non-200 reply each.

        Deliberately does NOT trust /shelly's 'num_outputs' field for
        either channel count - live-verified misleading: a Shelly Bulb
        Duo reports num_outputs=1 for its light output, but has no
        /relay/0 at all, only /light/0 (and conversely a relay device
        has no /light/0). Probing each endpoint is self-verifying: a
        200 reply only happens where that control surface genuinely
        exists. See _local/shelly_api.md for the live device data this
        is based on.
    """
    try:
        info = requests.get(f'http://{ip}/shelly', timeout=HTTP_TIMEOUT).json()
    except Exception:
        return None

    name = info.get('name')
    if 'gen' not in info:
        try:
            settings = requests.get(f'http://{ip}/settings', timeout=HTTP_TIMEOUT).json()
            name = settings.get('name')
        except Exception:
            pass

    def _count_channels(endpoint: str, cap: int) -> int:
        count = 0
        while count < cap:
            try:
                resp = requests.get(f'http://{ip}/{endpoint}/{count}', timeout=HTTP_TIMEOUT)
                if resp.status_code != 200:
                    break
            except Exception:
                break
            count += 1
        return count

    relays = _count_channels('relay', MAX_RELAY_CHANNELS)
    lights = _count_channels('light', MAX_LIGHT_CHANNELS)

    return {'ip': ip, 'name': name, 'type': info.get('type', info.get('model', 'unknown')),
           'relays': relays, 'lights': lights}


def _find_real_ports() -> dict[str, IoPort]:
    io_ports: dict[str, IoPort] = {}
    ips = _find_ips()
    if not ips:
        return io_ports

    devices: list[dict] = []
    lock = threading.Lock()

    def _probe(ip: str) -> None:
        dev = _identify(ip)
        if dev:
            with lock:
                devices.append(dev)

    threads = [threading.Thread(target=_probe, args=(ip,)) for ip in ips]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=HTTP_TIMEOUT * (MAX_RELAY_CHANNELS + 2))

    for dev in devices:
        label = dev['name'] or '%s (%s)' % (dev['type'], dev['ip'])
        for ch in range(dev['relays']):
            cfg = {'ip': dev['ip'], 'ch': ch}
            port_name = label if dev['relays'] == 1 else f'{label} relay {ch}'
            io_ports[port_name] = IoPort(PortFunc.Bout, DriverShellyRelay, cfg, [])
        for ch in range(dev['lights']):
            cfg = {'ip': dev['ip'], 'ch': ch}
            port_name = f'{label} dimmer' if dev['lights'] == 1 else f'{label} dimmer {ch}'
            io_ports[port_name] = IoPort(PortFunc.Aout, DriverShellyDimmer, cfg, [])
    return io_ports


def _find_fake_ports() -> dict[str, IoPort]:
    cfg = {'ip': '0.0.0.0', 'ch': 0, 'fake': True}
    return {
        '!Shelly #1': IoPort(PortFunc.Bout, DriverShellyRelay, cfg, []),
        '!Shelly #1 dimmer': IoPort(PortFunc.Aout, DriverShellyDimmer, cfg, []),
    }


_discovery_lock = threading.Lock()
_discovery_cache: dict[str, IoPort] | None = None


def _discover_all_ports() -> dict[str, IoPort]:
    """ the actual mDNS scan + per-device identify/probe, run at most
        once per process (memoized). DriverShellyRelay and
        DriverShellyDimmer both call this from their own find_ports()
        and filter to their own ports - this is the first driver
        module with more than one class sharing a single discovery
        pass, and having only one of the classes' find_ports() do the
        real work meant IoRegistry's startup log misattributed the
        other class' ports to it (e.g. "Discovering ... for
        DriverShellyRelay" while the reported ports also included a
        dimmer, which is really a DriverShellyDimmer port) - see
        _local/shelly_api.md.
    """
    global _discovery_cache
    with _discovery_lock:
        if _discovery_cache is None:
            if Zeroconf:
                io_ports = _find_real_ports()
            else:
                log.error('zeroconf is not installed, Shelly devices cannot be discovered')
                io_ports = {}
            if not io_ports:
                log.brief('Faking Shelly devices ...')
                io_ports = _find_fake_ports()
            _discovery_cache = io_ports
        return _discovery_cache


class _ShellyBase:
    """ shared find_ports() for every Shelly port-driver class in this
        file. Each subclass gets its own accurate, class-specific
        find_ports() (correct per-class discovery log line in
        IoRegistry) while the actual network scan runs at most once
        per process, memoized in _discover_all_ports() - see that
        function's docstring for why this exists (the first driver
        module here with more than one class sharing a single
        discovery pass).
    """
    _BUS = 'Shelly'

    @classmethod
    def find_ports(cls) -> dict[str, IoPort]:
        return {name: port for name, port in _discover_all_ports().items()
               if port.driver is cls}


class DriverShellyRelay(_ShellyBase, OutDriver):
    """ Binary relay output on a Shelly smart switch/plug, Gen1 or
        Gen2/Gen3 (SHSW-1, SHSW-25, SHPLG-S, Shelly Plus/Pro relays,
        ...), via the local HTTP API. Gen1's native relay control is
        GET /relay/<N>?turn=on|off; Gen2/Gen3 devices support this
        exact same endpoint through their documented backward-
        compatibility layer, live-confirmed working (not just
        documented) against a real Shelly Plus 2PM, so both
        generations share this one write path - see
        _local/shelly_api.md.

        Ain/Bin (temperature add-on inputs, digital inputs) are
        deliberately deferred - _identify()'s device record already
        carries what a future sibling driver class would need (ip,
        type, relays, lights), reusable without reshaping this code.
        DriverShellyDimmer (Aout, below) is the first such sibling.
    """

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self._ip: str = cfg['ip']
        self._ch: int = int(cfg['ch'])
        # network device: fake only when find_ports() explicitly marked
        # it so (discovery found nothing), never derived from is_raspi()
        self._fake: bool = bool(cfg.get('fake', False))
        self.name: str = 'Shelly(%s ch%d)' % (self._ip, self._ch)
        if self._fake:
            self.name = self._mark_fake(self.name)

    def write(self, value: bool) -> None:
        log.info('%s -> %d', self.name, bool(value))
        if not self._fake:
            turn = 'on' if value else 'off'
            try:
                resp = requests.get(f'http://{self._ip}/relay/{self._ch}',
                                    params={'turn': turn}, timeout=HTTP_TIMEOUT)
                resp.raise_for_status()
            except Exception:
                # a flaky network write must not crash the bus thread
                # that called SwitchDevice.write() -> this method
                log.exception('%s failed to send relay command', self.name)
        self._val = bool(value)

    def read(self) -> bool:
        if not self._fake:
            try:
                resp = requests.get(f'http://{self._ip}/relay/{self._ch}', timeout=HTTP_TIMEOUT)
                resp.raise_for_status()
                self._val = bool(resp.json().get('ison', self._val))
            except Exception:
                log.exception('%s failed to read relay state, returning last known', self.name)
        log.info('%s = %d', self.name, self._val)
        return bool(self._val)


class DriverShellyDimmer(_ShellyBase, OutDriver):
    """ Analog (0..100) dimmer output on a Shelly light/bulb (e.g.
        Shelly Bulb Duo), via GET /light/<N>. 0..100 maps 1:1 onto
        Shelly's own brightness range (already 0..100, live-confirmed
        - no scaling needed).

        On this device family, 'on/off' (ison) and 'brightness' are
        independent fields - live-confirmed setting brightness alone
        (no turn= param) does NOT change ison, and brightness is
        retained even while off. To give this Aout channel the usual
        "0 = off, >0 = on at that level" semantics (matching
        DriverPWM.write()'s hardware-enable convention elsewhere in
        this codebase), write() always sends turn= explicitly too,
        derived from value - live-confirmed a single combined
        'turn=on&brightness=N' request applies both correctly, no
        separate requests needed. See _local/shelly_api.md.
    """

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self._ip: str = cfg['ip']
        self._ch: int = int(cfg['ch'])
        self._fake: bool = bool(cfg.get('fake', False))
        self.name: str = 'Shelly(%s ch%d) dimmer' % (self._ip, self._ch)
        if self._fake:
            self.name = self._mark_fake(self.name)

    def write(self, value: float) -> None:
        value = max(0, min(100, round(value)))
        log.info('%s -> %d', self.name, value)
        if not self._fake:
            try:
                resp = requests.get(
                    f'http://{self._ip}/light/{self._ch}',
                    params={'turn': 'on' if value > 0 else 'off', 'brightness': value},
                    timeout=HTTP_TIMEOUT)
                resp.raise_for_status()
            except Exception:
                log.exception('%s failed to send dimmer command', self.name)
        self._val = value

    def read(self) -> float:
        if not self._fake:
            try:
                resp = requests.get(f'http://{self._ip}/light/{self._ch}', timeout=HTTP_TIMEOUT)
                resp.raise_for_status()
                status = resp.json()
                self._val = float(status.get('brightness', self._val)) if status.get('ison') else 0
            except Exception:
                log.exception('%s failed to read dimmer state, returning last known', self.name)
        log.info('%s = %d', self.name, self._val)
        return float(self._val)

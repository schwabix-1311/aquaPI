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
        'name' key via /shelly), then count relay channels by probing
        /relay/0.. until a non-200 reply.

        Deliberately does NOT trust /shelly's 'num_outputs' field for
        the channel count - live-verified misleading for non-relay
        output devices (e.g. a Shelly Bulb Duo reports num_outputs=1
        for its light output, but has no /relay/0 at all - only
        /light/0). Probing /relay/N is self-verifying: a 200 reply
        only happens where relay control genuinely exists. See
        _local/shelly_api.md for the live device data this is based on.
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

    relays = 0
    while relays < MAX_RELAY_CHANNELS:
        try:
            resp = requests.get(f'http://{ip}/relay/{relays}', timeout=HTTP_TIMEOUT)
            if resp.status_code != 200:
                break
        except Exception:
            break
        relays += 1

    return {'ip': ip, 'name': name, 'type': info.get('type', info.get('model', 'unknown')),
           'relays': relays}


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
    return io_ports


def _find_fake_ports() -> dict[str, IoPort]:
    cfg = {'ip': '0.0.0.0', 'ch': 0, 'fake': True}
    return {'!Shelly #1': IoPort(PortFunc.Bout, DriverShellyRelay, cfg, [])}


class DriverShellyRelay(OutDriver):
    """ Binary relay output on a Shelly smart switch/plug, Gen1 or
        Gen2/Gen3 (SHSW-1, SHSW-25, SHPLG-S, Shelly Plus/Pro relays,
        ...), via the local HTTP API. Gen1's native relay control is
        GET /relay/<N>?turn=on|off; Gen2/Gen3 devices support this
        exact same endpoint through their documented backward-
        compatibility layer, live-confirmed working (not just
        documented) against a real Shelly Plus 2PM, so both
        generations share this one write path - see
        _local/shelly_api.md.

        Only Bout is implemented so far. Ain/Aout/Bin (temperature
        add-on inputs, dimmers, digital inputs) are deliberately
        deferred - _identify()'s device record already carries what a
        future sibling driver class would need (ip, type, relays),
        reusable without reshaping this code, mirroring how
        DriverWlanAudioStation/-StationIn piggyback on
        DriverWlanAudioPower.find_ports() instead of each declaring
        their own.
    """

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        if Zeroconf:
            io_ports = _find_real_ports()
            if io_ports:
                return io_ports
        else:
            log.error('zeroconf is not installed, Shelly devices cannot be discovered')
        return _find_fake_ports()

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

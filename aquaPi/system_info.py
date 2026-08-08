#!/usr/bin/env python3

import os
import platform
import shutil

from flask import current_app


def get_system_stats() -> dict:
    """ collect a small set of system health stats for the footer status
        line - production is Raspberry Pi OS only, but the dev server
        also runs directly on Linux PCs, so this stays Linux-stdlib-only
        (no psutil dependency). Each stat is fetched independently, so a
        platform missing one (e.g. a Windows dev box has no
        os.getloadavg()/proc/meminfo) still gets the rest instead of a
        failed request - full non-Linux support isn't a goal, just not
        crashing outright.
    """
    try:
        os_name = platform.freedesktop_os_release().get('PRETTY_NAME', platform.platform())
    except OSError:
        os_name = platform.platform()  # non-Linux fallback, always available
    # PRETTY_NAME alone omits any version on rolling-release distros (e.g.
    # plain "Manjaro Linux") - platform.release() (kernel version, always
    # available, distro-agnostic) fills that gap even when it's somewhat
    # redundant with distros whose PRETTY_NAME already has a version in it
    os_name = f'{os_name} ({platform.release()})'

    # Raspberry Pi OS's own /etc/os-release identifies as plain "Debian
    # GNU/Linux" (a documented Raspberry Pi OS quirk - it really is
    # Debian-based, os-release just never says "Raspberry Pi OS"). The
    # device-tree model file gives the actual hardware instead, e.g.
    # "Raspberry Pi Zero 2 W Rev 1.0" - kept as its own field (hardware
    # platform, not OS) rather than folded into `os_name`. Doesn't exist
    # off Raspberry Pi hardware (dev PCs, Windows), so stays None there.
    hw_model = None
    try:
        with open('/proc/device-tree/model') as f:
            hw_model = f.read().strip('\x00').strip() or None
    except OSError:
        pass

    try:
        load1, _, _ = os.getloadavg()
        load1 = round(load1, 2)
    except (AttributeError, OSError):
        load1 = None  # not available on Windows

    mem_used_pct = None
    try:
        mem = {}
        with open('/proc/meminfo') as f:
            for line in f:
                key, _, rest = line.partition(':')
                mem[key] = int(rest.strip().split()[0])  # kB
        mem_total = mem['MemTotal']
        mem_used = mem_total - mem.get('MemAvailable', mem['MemFree'])
        mem_used_pct = round(mem_used / mem_total * 100, 1)
    except (FileNotFoundError, KeyError, ValueError):
        pass  # /proc/meminfo is Linux-only

    disk = shutil.disk_usage(current_app.config['INSTANCE_PATH'])  # cross-platform

    return {
        'os': os_name,
        'hw_model': hw_model,
        'load1': load1,
        'mem_used_pct': mem_used_pct,
        'cpu_count': os.cpu_count(),
        'disk_used_pct': round(disk.used / disk.total * 100, 1),
    }

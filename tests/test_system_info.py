#!/usr/bin/env python3
""" Tests for the swap-usage stat added to aquaPi/system_info.py for the
    footer status line (Footer improvement, 2026-08-12). The rest of
    get_system_stats() (OS name, HW model, load, RAM, disk) stays as
    untested as it already was - out of scope here, this only covers the
    new swap_used_pct logic.
"""

import builtins

from aquaPi.system_info import get_system_stats


_FAKE_MEMINFO_WITH_SWAP = """\
MemTotal:        8000000 kB
MemFree:         2000000 kB
MemAvailable:    4000000 kB
SwapTotal:       2000000 kB
SwapFree:         500000 kB
"""

_FAKE_MEMINFO_NO_SWAP = """\
MemTotal:        8000000 kB
MemFree:         2000000 kB
MemAvailable:    4000000 kB
SwapTotal:              0 kB
SwapFree:               0 kB
"""


def _patch_meminfo(monkeypatch, content):
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if path == '/proc/meminfo':
            from io import StringIO
            return StringIO(content)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', fake_open)


def test_swap_used_pct_computed_from_proc_meminfo(minimal_app, monkeypatch):
    _patch_meminfo(monkeypatch, _FAKE_MEMINFO_WITH_SWAP)

    with minimal_app.app_context():
        stats = get_system_stats()

    assert stats['swap_used_pct'] == 75.0


def test_swap_used_pct_is_none_when_no_swap_configured(minimal_app, monkeypatch):
    _patch_meminfo(monkeypatch, _FAKE_MEMINFO_NO_SWAP)

    with minimal_app.app_context():
        stats = get_system_stats()

    assert stats['swap_used_pct'] is None

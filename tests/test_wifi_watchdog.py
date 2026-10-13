#!/usr/bin/env python3
""" Tests for tools/wifi-watchdog/wifi-watchdog: the real bash script, run
    against fake ip/ping/modprobe/systemctl/logger/sleep commands that only
    record their calls - no network, driver or reboot is touched.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / 'tools' / 'wifi-watchdog' / 'wifi-watchdog'

FAKE = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "$CALLS"
case "$(basename "$0")" in
  ip)   [ -n "$FAKE_GATEWAY" ] && echo "default via $FAKE_GATEWAY dev wlan0 proto dhcp" ;;
  ping) exit "$FAKE_PING_RC" ;;
esac
exit 0
"""


@pytest.fixture
def watchdog(tmp_path):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for cmd in ('ip', 'ping', 'modprobe', 'systemctl', 'logger', 'sleep'):
        (bin_dir / cmd).write_text(FAKE)
        (bin_dir / cmd).chmod(0o755)
    sys_net = tmp_path / 'net'
    sys_net.mkdir()
    (sys_net / 'wlan0').mkdir()
    calls = tmp_path / 'calls'

    def run(gateway='192.168.1.1', ping_rc=0, iface_present=True):
        if not iface_present and (sys_net / 'wlan0').exists():
            (sys_net / 'wlan0').rmdir()
        calls.write_text('')
        env = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}', CALLS=str(calls),
                   FAKE_GATEWAY=gateway, FAKE_PING_RC=str(ping_rc),
                   STATE_DIR=str(tmp_path / 'state'), SYS_NET=str(sys_net),
                   REBOOT_STAMP=str(tmp_path / 'lib' / 'last-reboot'))
        subprocess.run(['bash', str(SCRIPT)], env=env, check=True, timeout=10)
        return calls.read_text().splitlines()

    run.stamp = tmp_path / 'lib' / 'last-reboot'
    return run


def _did(calls, cmd):
    return [c for c in calls if c.startswith(cmd)]


def test_healthy_network_does_nothing(watchdog):
    calls = watchdog()
    assert not _did(calls, 'modprobe') and not _did(calls, 'systemctl')


def test_driver_reload_after_two_failures(watchdog):
    first = watchdog(ping_rc=1)
    assert not _did(first, 'modprobe')
    second = watchdog(ping_rc=1)
    assert _did(second, 'modprobe') == [
        'modprobe -r brcmfmac_wcc', 'modprobe -r brcmfmac',     # unload: dependent first
        'modprobe brcmfmac', 'modprobe brcmfmac_wcc']           # load: reverse order


def test_recovery_resets_the_counter(watchdog):
    watchdog(ping_rc=1)
    back = watchdog()
    assert any('network back after 1' in c for c in back)
    again = watchdog(ping_rc=1)       # a fresh first failure: no reload yet
    assert not _did(again, 'modprobe')


def test_router_down_never_reboots(watchdog):
    # interface still there, gateway silent: only repeated driver reloads
    calls = [watchdog(ping_rc=1) for _ in range(8)]
    assert not any(_did(c, 'systemctl') for c in calls)
    assert sum(1 for c in calls if _did(c, 'modprobe')) == 4   # every 2nd run


def test_missing_interface_reboots_once_per_gap(watchdog):
    runs = [watchdog(gateway='', iface_present=False) for _ in range(5)]
    assert _did(runs[-1], 'systemctl') == ['systemctl reboot']
    assert watchdog.stamp.exists()
    # right after a watchdog reboot (stamp is fresh) it must not loop
    after = [watchdog(gateway='', iface_present=False) for _ in range(5)]
    assert not any(_did(c, 'systemctl') for c in after)
    assert any('not rebooting' in c for c in after[-1])


def test_old_reboot_stamp_allows_the_next_reboot(watchdog):
    watchdog.stamp.parent.mkdir(parents=True)
    watchdog.stamp.write_text(str(int(time.time()) - 7 * 3600))
    runs = [watchdog(gateway='', iface_present=False) for _ in range(5)]
    assert _did(runs[-1], 'systemctl') == ['systemctl reboot']

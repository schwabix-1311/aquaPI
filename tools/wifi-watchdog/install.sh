#!/usr/bin/env bash
# Installs (or with --uninstall removes) the WiFi watchdog on this Pi.
# Needs sudo. Log: journalctl -t wifi-watchdog
set -euo pipefail
cd "$(dirname "$0")"

if [ "${1:-}" = "--uninstall" ]; then
    sudo systemctl disable --now wifi-watchdog.timer || true
    sudo rm -f /etc/systemd/system/wifi-watchdog.service /etc/systemd/system/wifi-watchdog.timer \
               /usr/local/sbin/wifi-watchdog
    sudo systemctl daemon-reload
    echo "wifi-watchdog removed."
    exit 0
fi

sudo install -m 755 wifi-watchdog /usr/local/sbin/wifi-watchdog
sudo install -m 644 wifi-watchdog.service wifi-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wifi-watchdog.timer
systemctl list-timers wifi-watchdog.timer --no-pager
echo "Installed. Log: journalctl -t wifi-watchdog"

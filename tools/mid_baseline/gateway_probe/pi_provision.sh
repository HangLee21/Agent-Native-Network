#!/usr/bin/env bash
# Provision a Raspberry Pi as a standalone EoRa edge node.
#
# Runs on the Pi itself (sudo). Idempotent: safe to re-run. Everything it changes is either
# reversible with nmcli/systemctl or a plain file, and nothing depends on a specific IP
# address being available anywhere.
#
#   sudo ./pi_provision.sh eora-air-02
#
# Design rule: never hard-code an address. The Pi asks for DHCP when a router exists and
# falls back to link-local (169.254/16) when none does, and avahi makes it reachable by
# name in both cases, so the same image works on the bench and in the air.
set -euo pipefail

HOSTNAME_TARGET="${1:-}"
WIFI_SSID="${2:-}"
if [[ -z "$HOSTNAME_TARGET" ]]; then
	echo "usage: sudo $0 <hostname> [wifi-ssid]" >&2
	echo "  e.g. sudo $0 eora-air-02 hli21" >&2
	exit 2
fi

log() { printf '\n== %s\n' "$*"; }

log "hostname -> $HOSTNAME_TARGET"
if [[ "$(hostname)" != "$HOSTNAME_TARGET" ]]; then
	hostnamectl set-hostname "$HOSTNAME_TARGET"
	# keep /etc/hosts coherent so sudo does not stall on name resolution
	if ! grep -q "127.0.1.1[[:space:]]*$HOSTNAME_TARGET" /etc/hosts; then
		sed -i "/^127\.0\.1\.1/d" /etc/hosts
		echo "127.0.1.1	$HOSTNAME_TARGET" >>/etc/hosts
	fi
fi

log "ethernet: DHCP with link-local fallback (no static address anywhere)"
CONNECTION="$(nmcli -t -f NAME,DEVICE connection show --active | awk -F: '$2=="eth0"{print $1; exit}')"
if [[ -z "$CONNECTION" ]]; then
	CONNECTION="Wired connection 1"
fi
nmcli connection modify "$CONNECTION" ipv4.method auto
nmcli connection modify "$CONNECTION" ipv4.link-local fallback
nmcli connection modify "$CONNECTION" ipv6.method auto

log "boot path: skip network-online wait and cloud-init (nothing here needs them)"
systemctl disable NetworkManager-wait-online.service >/dev/null 2>&1 || true
touch /etc/cloud/cloud-init.disabled
systemctl disable --now cloud-init-network.service >/dev/null 2>&1 || true

log "mDNS so the device is reachable by name, not by address"
systemctl enable --now avahi-daemon >/dev/null 2>&1 || true

log "timezone"
timedatectl set-timezone Asia/Shanghai

log "serial tooling"
apt-get update -qq
apt-get install -y -qq python3-serial >/dev/null
usermod -aG dialout "${SUDO_USER:-eora}"

if [[ -n "$WIFI_SSID" ]]; then
	log "wifi (WPA2 personal): $WIFI_SSID"
	# The passphrase is entered here, not stored in this file or in shell history.
	read -r -s -p "WiFi 密码: " WIFI_PSK
	printf '\n'
	if [[ -n "$WIFI_PSK" ]]; then
		nmcli radio wifi on >/dev/null 2>&1 || true
		nmcli connection delete "wifi-$WIFI_SSID" >/dev/null 2>&1 || true
		nmcli connection add type wifi con-name "wifi-$WIFI_SSID" ifname wlan0 \
			ssid "$WIFI_SSID" \
			wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$WIFI_PSK" >/dev/null
		# Prefer WiFi for the default route; the wired link only carries the local gateway.
		nmcli connection modify "wifi-$WIFI_SSID" ipv4.route-metric 100
		nmcli connection up "wifi-$WIFI_SSID" >/dev/null 2>&1 || true
		unset WIFI_PSK
	else
		echo "  跳过（未输入密码）"
	fi
fi

log "state"
printf '  hostname   : %s\n' "$(hostname)"
printf '  managed by : %s\n' "$(nmcli -f GENERAL.STATE device show eth0 | awk -F: '{print $2}' | xargs)"
printf '  addresses  : %s\n' "$(ip -4 -o addr show eth0 | awk '{print $4}' | paste -sd, -)"
printf '  mDNS       : %s\n' "$(systemctl is-active avahi-daemon)"
printf '  serial     : %s\n' "$(ls /dev/serial/by-id/ 2>/dev/null | paste -sd, - || echo none)"

log "done: reach it as $(hostname).local (works with or without DHCP)"

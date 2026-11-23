#!/usr/bin/env bash
# Join one Raspberry Pi to the tailnet with no browser step.
#
#   sudo ./pi_enroll.sh eora-air-04 tskey-auth-xxxxxxxx
#
# Run it on the Pi itself (it needs sudo). It is safe to re-run.
#
# What it fixes beyond `tailscale up`, all learned the hard way on this bench:
#   * campus IPv6 is often unrouted while DNS still returns AAAA records first, so installs
#     and enrollment hang until IPv4 is preferred explicitly;
#   * a node key silently expires after ~180 days, so expiry is reported at the end for the
#     admin console rather than discovered in the field.
set -euo pipefail

HOSTNAME_TARGET="${1:-}"
AUTH_KEY="${2:-}"
if [[ -z "$HOSTNAME_TARGET" || -z "$AUTH_KEY" ]]; then
	echo "usage: sudo $0 <hostname> <authkey>" >&2
	exit 2
fi

if [[ "${EUID}" -ne 0 ]]; then
	echo "run with sudo" >&2
	exit 2
fi

log() { printf '\n== %s\n' "$*"; }

log "hostname"
hostnamectl set-hostname "$HOSTNAME_TARGET"
grep -q "127.0.1.1[[:space:]]*$HOSTNAME_TARGET" /etc/hosts || {
	sed -i "/^127\.0\.1\.1/d" /etc/hosts
	echo "127.0.1.1	$HOSTNAME_TARGET" >>/etc/hosts
}

log "prefer IPv4 (campus AAAA records often lead nowhere)"
grep -q '^precedence ::ffff:0:0/96' /etc/gai.conf 2>/dev/null || \
	echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf

log "tailscale package"
if ! command -v tailscale >/dev/null; then
	curl -fsSL https://tailscale.com/install.sh | sh
fi

log "enroll"
tailscale up --auth-key="$AUTH_KEY" --hostname="$HOSTNAME_TARGET" --accept-dns=false
sleep 3
tailscale ip -4 || true

log "state"
printf '  hostname : %s\n' "$(hostname)"
printf '  tailnet  : %s\n' "$(tailscale ip -4 2>/dev/null || echo none)"
printf '  peer seen: %s\n' "$(tailscale status 2>/dev/null | head -1 | awk '{print $1, $2}')"
printf '  node key : %s\n' "$(tailscale status --json 2>/dev/null | grep -o '"KeyExpiry":"[^"]*"' | head -1 | cut -d'"' -f4 || echo unknown)"

cat <<'NOTE'

== done
The device is reachable as <hostname> from any machine on the tailnet.
Remember: a node key expires by default (~180 days). For long-lived field units, disable
key expiry for this device in the admin console, or enroll with a tag.
NOTE

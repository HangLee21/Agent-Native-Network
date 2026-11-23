#!/usr/bin/env bash
# Join a WPA2-Enterprise (802.1X / PEAP-MSCHAPv2) network such as Tsinghua-Secure.
#
# Credentials are read here, interactively and without echo, and go straight into the
# NetworkManager connection profile (root-only file). They never appear on the command line,
# in this script, or in shell history.
#
#   sudo ./pi_wifi_8021x.sh                       # defaults to Tsinghua-Secure
#   sudo ./pi_wifi_8021x.sh eduroam
#
# Why 802.1X and not the open SSIDs: "Tsinghua-IPv4"/"Tsinghua-IPv6" only authenticate over a
# captive portal, which needs a browser. An unattended drone cannot log in that way.
set -euo pipefail

SSID="${1:-Tsinghua-Secure}"
CON="wifi-$SSID"
IFACE="wlan0"

if [[ "${EUID}" -ne 0 ]]; then
	echo "run with sudo" >&2
	exit 2
fi

printf 'SSID      : %s\n' "$SSID"
read -r -p '学号/账号 : ' IDENTITY
read -r -s -p '密码      : ' PASSWORD
printf '\n'

if [[ -z "$IDENTITY" || -z "$PASSWORD" ]]; then
	echo "账号或密码为空，退出" >&2
	exit 2
fi

echo "== 移除同名旧配置（如有）"
nmcli connection delete "$CON" >/dev/null 2>&1 || true

echo "== 创建 802.1X 配置（PEAP / MSCHAPv2）"
nmcli connection add type wifi con-name "$CON" ifname "$IFACE" ssid "$SSID" \
	802-11-wireless-security.key-mgmt wpa-eap \
	802-11-wireless-security.pmf 1 \
	802-1x.eap peap \
	802-1x.phase2-auth mschapv2 \
	802-1x.identity "$IDENTITY" \
	802-1x.password "$PASSWORD" >/dev/null

# Prefer WiFi for the default route, keep the wired link for the LoRa gateway.
nmcli connection modify "$CON" ipv4.route-metric 100
nmcli connection modify "$CON" ipv6.route-metric 100
nmcli connection modify "Wired connection 1" ipv4.route-metric 500 2>/dev/null || true

echo "== 连接（最多等 30 秒）"
nmcli connection up "$CON" >/dev/null 2>&1 || true
for _ in $(seq 1 15); do
	if ip -4 -o addr show "$IFACE" 2>/dev/null | grep -q 'inet '; then
		break
	fi
	sleep 2
done

echo
echo "== 结果"
printf '  wlan0 地址 : %s\n' "$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{print $4}' | paste -sd, - || echo 无)"
printf '  默认路由   : %s\n' "$(ip route show default | head -1)"
printf '  连接状态   : %s\n' "$(nmcli -f GENERAL.STATE device show "$IFACE" | awk -F: '{print $2}' | xargs)"

if ! ip -4 -o addr show "$IFACE" 2>/dev/null | grep -q 'inet '; then
	cat <<'HINT'

== 没拿到地址时的排查顺序
  1) 看认证失败原因（最常见：密码错、或学校要求指定 CA）
       sudo journalctl -u NetworkManager -n 40 --no-pager | grep -iE '802-1x|eap|fail'
  2) 很多校园网要求验证服务器证书，补一条：
       sudo nmcli connection modify <连接名> 802-1x.domain-suffix-match tsinghua.edu.cn
     若仍失败，可临时关闭证书校验定位问题（仅测试用）：
       sudo nmcli connection modify <连接名> 802-1x.phase1-peapver 0
  3) 换 eduroam 试：账号同样格式，若 eduroam 能通说明账号没问题
  4) 开放 SSID（Tsinghua-IPv4）需要网页登录，不适合无人值守
HINT
fi

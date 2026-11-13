#!/bin/sh
# Read-only inventory of a Raspberry Pi based LoRa gateway.
#
# Prints what is needed to fill docs/LORA_GATEWAY_PARAMETERS.md. It writes nothing,
# installs nothing and restarts nothing: only `cat`, `ls`, `find`, `uname` are used.
# Run on the gateway itself (or over ssh):
#
#   sh pi_dump.sh > gateway-inventory.txt
#
echo "=== 1. system ==="
uname -a
[ -r /etc/os-release ] && head -3 /etc/os-release
echo
echo "=== 2. board ==="
[ -r /proc/device-tree/model ] && tr -d '\0' < /proc/device-tree/model && echo
grep -m1 -E '^(Model|Hardware|Revision)' /proc/cpuinfo 2>/dev/null
echo
echo "=== 3. serial / spi devices ==="
ls -l /dev/spidev* 2>/dev/null
ls -l /dev/ttyAMA0 /dev/ttyS0 /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
echo
echo "=== 4. lorawan / concentrator software ==="
for p in lora_pkt_fwd ttn-pkt-forwarder reset_lgw.sh util_chip_id; do
  command -v "$p" 2>/dev/null
done
find /opt /usr/local /etc -maxdepth 3 -type d \( -iname '*lora*' -o -iname '*rak*' -o -iname '*ttn*' \
     -o -iname '*chirpstack*' -o -iname '*dragino*' -o -iname '*milesight*' \) 2>/dev/null
echo
echo "=== 5. concentrator config files ==="
find /opt /usr/local /etc -maxdepth 4 -type f \( -name 'global_conf.json' -o -name 'local_conf.json' \
     -o -name '*pkt_fwd*' -o -name 'station.conf' \) 2>/dev/null
echo
echo "=== 6. key radio parameters (raw) ==="
for f in $(find /opt /usr/local /etc -maxdepth 4 -type f -name 'global_conf.json' 2>/dev/null); do
  echo "--- $f ---"
  cat "$f"
  echo
done
for f in $(find /opt /usr/local /etc -maxdepth 4 -type f -name 'local_conf.json' 2>/dev/null); do
  echo "--- $f ---"
  cat "$f"
  echo
done
echo
echo "=== 7. network ==="
ip -4 addr show 2>/dev/null | grep -E 'inet |^[0-9]+:'
ip -6 addr show 2>/dev/null | grep -E 'inet6 '
ip -4 route show 2>/dev/null
echo
echo "=== 8. services that own the concentrator ==="
ps -eo pid,comm,args 2>/dev/null | grep -Ei 'lora|pkt_fwd|chirp|gateway' | grep -v grep
echo
echo "=== 9. listening sockets ==="
(ss -lntup 2>/dev/null || netstat -lntup 2>/dev/null) | head -40
echo
echo "=== 10. recent gateway log lines ==="
for f in /var/log/*lora* /var/log/*pkt_fwd*; do
  [ -r "$f" ] && echo "--- $f (tail 20) ---" && tail -20 "$f"
done
echo
echo "=== done (read-only) ==="

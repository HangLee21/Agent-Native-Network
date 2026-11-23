facts=$(PATH=/usr/sbin:/usr/bin:/sbin:/bin:$PATH; export PATH
printf "CONNECTION %s\n" "$SSH_CONNECTION"
printf "ARCH "; uname -m
if command -v dpkg >/dev/null 2>&1; then printf "DPKG_ARCH "; dpkg --print-architecture; fi
if [ -r /etc/os-release ]; then sed -n 's/^PRETTY_NAME=/OS /p' /etc/os-release; fi
for n in sudo systemctl dnsmasq ip tar base64; do command -v "$n" >/dev/null 2>&1 || printf "MISSING %s\n" "$n"; done
s=$(command -v sudo 2>/dev/null || true); [ -z "$s" ] || printf "SUDO_PATH %s\n" "$s"
command -v systemctl >/dev/null 2>&1 && systemctl --version 2>/dev/null | sed -n '1s/^/SYSTEMD_VERSION /p'
command -v dnsmasq >/dev/null 2>&1 && dnsmasq --version 2>/dev/null | sed -n '1s/^/DNSMASQ_VERSION /p'
if command -v dpkg-query >/dev/null 2>&1; then dpkg-query -W -f='PKG ${Package} ${Version} ${Status}\n' python3 python3-minimal python3.4 python3.4-minimal libpython3.4-minimal libpython3.4-stdlib dnsmasq dnsmasq-base systemd libc6 2>/dev/null || true; fi
found=0; had_python=0
for p in "$(command -v python3 2>/dev/null || true)" /usr/bin/python3.4 /usr/local/bin/python3.4; do
  [ -n "$p" ] && [ -x "$p" ] || continue
  had_python=1
  version=$("$p" -c 'import argparse,base64,hashlib,ipaddress,json,os,pathlib,re,shutil,socket,subprocess,sys,tempfile,time,urllib.request,uuid; print("%d.%d.%d" % sys.version_info[:3]); sys.exit(0 if sys.version_info >= (3,4) else 1)' 2>/dev/null) || continue
  printf "PY_PATH %s\nPY_VERSION %s\nPY_OK\n" "$p" "$version"; found=1; break
done
if [ "$found" = 0 ]; then if [ "$had_python" = 0 ]; then printf "MISSING python3\n"; else printf "MISSING python3_compatible\n"; fi; fi
for p in /sys/class/net/*; do n=${p##*/}; [ "$n" = lo ] && continue; [ -d "$p/wireless" ] && continue; [ "$(cat "$p/type")" = 1 ] || continue; ip -o -4 addr show dev "$n" | awk -v n="$n" '{print "ADDRESS " n " " $4}'; done)
printf '%s\n' "$facts"
missing=$(printf '%s\n' "$facts" | grep '^MISSING '  || true)
[ -z "$missing" ] || { echo '缺少网关运行组件，未安装；请将诊断日志交给技术支持'; exit 20; }
py=$(printf '%s\n' "$facts" | sed -n 's/^PY_PATH //p'); sudo_path=$(printf '%s\n' "$facts" | sed -n 's/^SUDO_PATH //p')
printf '%s\n' "$facts" | grep -qx PY_OK || { echo 'Python版本或依赖不兼容，未安装'; exit 20; }
printf '%s\n' "$py" "$sudo_path" | grep -Eqv '^/[A-Za-z0-9_./+-]+$' && { echo '运行程序路径无效，未安装'; exit 20; }
[ -n "$py" ] && [ -n "$sudo_path" ] || exit 20
set -- $SSH_CONNECTION; server=$3; iface=$(printf '%s\n' "$facts" | awk -v h='192.168.137.200' -v s="$server" '$1=="ADDRESS" {split($3,a,"/"); if(a[1]==h && a[1]==s) print $2}' | sort -u); [ "$(printf '%s\n' "$iface" | grep -c .)" = 1 ] || { echo '无法唯一确认网关专用网口，未更改网关'; exit 22; }
echo '网关环境检查通过，正在安装；如要求管理员密码，请输入后按回车。'
set -e; mkdir -m 700 /tmp/ann-gateway-0edc4a0fae2a4663af2b6bfa19ee08db; trap 'rm -rf /tmp/ann-gateway-0edc4a0fae2a4663af2b6bfa19ee08db' EXIT; printf '%s' 'PAYLOAD' | base64 -d | tar -xzm -C /tmp/ann-gateway-0edc4a0fae2a4663af2b6bfa19ee08db
"$sudo_path" "$py" /tmp/ann-gateway-0edc4a0fae2a4663af2b6bfa19ee08db/linux_installer.py install --package /tmp/ann-gateway-0edc4a0fae2a4663af2b6bfa19ee08db --interface "$iface" --gateway-eui b827ebfffe32e2c1 --dedicated

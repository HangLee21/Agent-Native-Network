set -eu
stage=$1; runtime_archive=$2; runtime_hash=$3; service_archive=$4; service_hash=$5; action=$6; iface=$7; eui=$8
runtime=/opt/ann-gateway/runtime/jessie-armhf-v1
trap 'rm -rf "$stage/service"; rm -f "$stage/dnsmasq-test.conf"' EXIT
[ "$(sha256sum "$runtime_archive" | awk '{print $1}')" = "$runtime_hash" ] || { echo '运行环境校验失败'; exit 31; }
[ "$(sha256sum "$service_archive" | awk '{print $1}')" = "$service_hash" ] || { echo '服务包校验失败'; exit 31; }
mkdir -p /opt/ann-gateway/runtime
if [ -e "$runtime" ]; then
  [ -f "$runtime/.archive-sha256" ] && [ "$(cat "$runtime/.archive-sha256")" = "$runtime_hash" ] || { echo '运行环境目录已存在且无法确认'; exit 32; }
  tar -dzf "$runtime_archive" -C "$runtime" >/dev/null || { echo '已有运行环境校验失败'; exit 32; }
else
  mkdir -m 755 "$runtime"
  tar -xzf "$runtime_archive" -C "$runtime" || { rm -rf "$runtime"; echo '运行环境解包失败'; exit 33; }
  printf '%s\n' "$runtime_hash" > "$runtime/.archive-sha256"
fi
mkdir -m 700 "$stage/service"
tar -xzf "$service_archive" -C "$stage/service"
printf 'port=0\n' > "$stage/dnsmasq-test.conf"
"$runtime/bin/python3" -B -c 'import sys,argparse,base64,hashlib,ipaddress,json,pathlib,urllib.request; assert sys.version_info >= (3,4)'
PYTHONPATH="$stage/service/services" "$runtime/bin/python3" -B -c 'import tools.flight_link.appliance'
"$runtime/bin/dnsmasq" --version >/dev/null
"$runtime/bin/dnsmasq" --test --conf-file="$stage/dnsmasq-test.conf"
if [ "$action" = install ]; then
  "$runtime/bin/python3" -B "$stage/service/linux_installer.py" install --package "$stage/service" --interface "$iface" --gateway-eui "$eui" --dedicated --python-wrapper "$runtime/bin/python3" --dnsmasq-wrapper "$runtime/bin/dnsmasq"
else
  "$runtime/bin/python3" -B "$stage/service/linux_installer.py" rollback
fi

"""Install a verified, private gateway runtime through one SSH transport."""
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import tarfile
import tempfile
import uuid
import ssh_transport as ssh

ROOT=Path(__file__).resolve().parents[2]
RUNTIME_ROOT='/opt/ann-gateway/runtime/jessie-armhf-v1'

class DeployError(RuntimeError):pass


def load_runtime():
    base=ROOT/'runtime/gateway'
    m=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    if m.get('runtime_id')!='jessie-armhf-v1' or m.get('install_root')!=RUNTIME_ROOT or m.get('entrypoints')!={'python':'bin/python3','dnsmasq':'bin/dnsmasq'}:
        raise DeployError('网关离线运行环境清单不匹配')
    name=m.get('archive_filename','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.tar\.gz',name):raise DeployError('运行环境文件名无效')
    path=base/name
    if not path.is_file() or path.stat().st_size!=m.get('archive_size'):raise DeployError('离线运行环境缺失或大小不符')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=m.get('archive_sha256'):raise DeployError('离线运行环境校验失败')
    with tarfile.open(str(path),'r:gz') as tar:
        for item in tar:
            name=item.name
            if name.startswith('/') or '..' in name.split('/') or not (item.isfile() or item.isdir() or item.issym() or item.islnk()):raise DeployError('运行环境归档包含无效路径')
            if item.issym() or item.islnk():
                target=item.linkname
                resolved=posixpath.normpath(posixpath.join(posixpath.dirname(name),target) if item.issym() else target)
                if target.startswith('/') or resolved=='..' or resolved.startswith('../'):raise DeployError('运行环境归档包含无效链接')
    return m,path,digest


EXTRA_PREFLIGHT="""
LC_ALL=C; export LC_ALL
[ -e /lib/ld-linux-armhf.so.3 ] && echo LOADER_OK || echo LOADER_MISSING
for n in sha256sum df awk grep sed sort; do command -v "$n" >/dev/null 2>&1 || printf 'MISSING %s\n' "$n"; done
opt=$(df -Pk /opt 2>/dev/null | awk 'NR==2 && NF>=6 && $4 ~ /^[0-9]+$/ {print $4}')
space_for_stage() {
  if [ ! -d "$1" ] || [ ! -w "$1" ]; then printf UNWRITABLE; return; fi
  value=$(df -Pk "$1" 2>/dev/null | awk 'NR==2 && NF>=6 && $4 ~ /^[0-9]+$/ {print $4}')
  printf '%s' "${value:-INVALID}"
}
tmp=$(space_for_stage /tmp)
vartmp=$(space_for_stage /var/tmp)
printf 'SPACE_OPT %s\n' "${opt:-INVALID}"
printf 'SPACE_TMP %s\n' "${tmp:-INVALID}"
printf 'SPACE_VARTMP %s\n' "${vartmp:-INVALID}"
"""


def validate_target(text,minimum,tmp_minimum=None):
    lines=text.splitlines()
    if 'ARCH armv7l' not in lines or 'DPKG_ARCH armhf' not in lines or 'LOADER_OK' not in lines:raise DeployError('网关架构或 ARM 加载器不匹配')
    if not any(x.startswith('OS ') and 'Raspbian GNU/Linux 8' in x for x in lines):raise DeployError('网关系统版本不匹配')
    if not any(x.startswith('PKG libc6 2.19-18+deb8u7 ') and x.endswith('install ok installed') for x in lines):raise DeployError('网关系统 C 库版本未确认，未安装')
    if not any(x.startswith('SYSTEMD_VERSION systemd 215') for x in lines):raise DeployError('网关 systemd 版本未确认')
    missing=[x[8:] for x in lines if x.startswith('MISSING ') and x[8:] not in ('python3','python3_compatible','dnsmasq')]
    if missing:raise DeployError('网关缺少基本工具：'+', '.join(missing))
    sudo_paths=[x[10:] for x in lines if x.startswith('SUDO_PATH ')]
    if len(sudo_paths)!=1 or not re.fullmatch(r'/[A-Za-z0-9_./+-]+',sudo_paths[0]):raise DeployError('无法确认网关管理员程序路径')
    if tmp_minimum is None:tmp_minimum=minimum
    def available(prefix):
        found=[x[len(prefix):] for x in lines if x.startswith(prefix)]
        return int(found[0])*1024 if len(found)==1 and found[0].isdigit() else None
    opt=available('SPACE_OPT ')
    if opt is None:raise DeployError('无法读取网关 /opt 可用空间（需要至少 {:.1f} MiB）'.format(minimum/1048576))
    if opt<minimum:raise DeployError('网关 /opt 空间不足：可用 {:.1f} MiB，需要 {:.1f} MiB'.format(opt/1048576,minimum/1048576))
    locations=[('/tmp',available('SPACE_TMP ')),('/var/tmp',available('SPACE_VARTMP '))]
    for path,size in locations:
        if size is not None and size>=tmp_minimum:return sudo_paths[0],path
    details='；'.join(path+' '+('不可写或无法读取' if size is None else '可用 {:.1f} MiB'.format(size/1048576)) for path,size in locations)
    if all(size is None for _,size in locations):raise DeployError('无法读取可写的网关暂存空间：'+details+'；需要 {:.1f} MiB'.format(tmp_minimum/1048576))
    raise DeployError('网关暂存空间不足或不可用：'+details+'；需要 {:.1f} MiB'.format(tmp_minimum/1048576))


ROOT_SCRIPT=r'''set -eu
umask 022
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
'''


def deploy(user,host,action,interface,eui,api):
    manifest,runtime,digest=load_runtime()
    # Locally package only the already verified service; no secrets enter the archive.
    with tempfile.TemporaryDirectory(prefix='ann-gateway-') as temp:
        root=Path(temp);package=root/'package';package.mkdir()
        if action=='install':api.prepare(package)
        else:
            import shutil
            shutil.copyfile(ROOT/'app/gateway_setup/linux_installer.py',package/'linux_installer.py')
        archive=root/'service.tar.gz';archive.write_bytes(api.package_bytes(package))
        service_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
        # /tmp holds both compressed archives and the extracted service files;
        # the much larger private runtime is unpacked only under /opt.
        service_unpacked=sum(p.stat().st_size for p in package.rglob('*') if p.is_file())
        tmp_minimum=runtime.stat().st_size+archive.stat().st_size+service_unpacked+8*1024*1024
        client,password=ssh.connect(host,user)
        created=False;sudo_started=False;finished=False
        try:
            text=ssh.readonly_command(client,api.PREFLIGHT+EXTRA_PREFLIGHT)
            api.log_preflight(text+'\nSPACE_OPT_REQUIRED '+str(int(manifest['minimum_free_bytes']))+'\nSPACE_TMP_REQUIRED '+str(tmp_minimum))
            sudo_path,stage_base=validate_target(text,int(manifest['minimum_free_bytes']),tmp_minimum)
            stage=stage_base+'/ann-gateway-'+uuid.uuid4().hex
            remote_runtime=stage+'/runtime.tar.gz';remote_service=stage+'/service.tar.gz'
            if action=='install' and interface is None:interface=api.choose_remote_interface(text,host)
            if interface is None:interface='eth0'
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}',interface):raise DeployError('网关网口无效')
            sftp=ssh.open_sftp_bounded(client)
            try:ssh.sftp_call(client,lambda:sftp.mkdir(stage,0o700));created=True
            finally:ssh.sftp_call(client,sftp.close)
            print('正在传输网关离线运行环境，请稍候。',flush=True)
            ssh.upload_verified(client,runtime,remote_runtime,digest)
            ssh.upload_verified(client,archive,remote_service,service_hash)
            print('检查通过，正在初始化网关。',flush=True)
            sudo_started=True
            ssh.sudo_command(client,['/bin/sh','-c',ROOT_SCRIPT,'ann-setup',stage,remote_runtime,digest,remote_service,service_hash,action,interface,eui],password,timeout=300,sudo_path=sudo_path)
            finished=True
        finally:
            password=None
            transport=client.get_transport()
            if created and (not sudo_started or finished) and transport and transport.is_active():
                try:
                    sftp=ssh.open_sftp_bounded(client)
                    try:
                        for path in (remote_runtime,remote_service):
                            try:ssh.sftp_call(client,lambda:sftp.remove(path))
                            except IOError:pass
                        ssh.sftp_call(client,lambda:sftp.rmdir(stage))
                    finally:ssh.sftp_call(client,sftp.close)
                except Exception:pass
            ssh.close_bounded(client)

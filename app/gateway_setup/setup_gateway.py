"""Create a verified gateway package and run interactive OpenSSH; no passwords are saved."""
import argparse
import base64
import gzip
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
class SetupError(RuntimeError):pass
LOG_FILE=None
SSH_OPTIONS=['-o','ConnectTimeout=5','-o','ConnectionAttempts=1']


def log_event(stage,status,code=None,error=None):
    if not LOG_FILE:return
    event={'time':time.strftime('%Y-%m-%dT%H:%M:%S'),'component':'setup','stage':stage,'status':status}
    if code is not None:event['exit_code']=code
    if error is not None:event['error_type']=error
    try:
        with open(LOG_FILE,'a',encoding='utf-8') as stream:stream.write(json.dumps(event,ensure_ascii=True)+'\n')
    except OSError:pass


def run_step(runner,stage,args,**kwargs):
    log_event(stage,'started')
    try:result=runner(args,**kwargs)
    except subprocess.CalledProcessError as exc:
        log_event(stage,'failed',code=exc.returncode,error=type(exc).__name__);raise
    except OSError as exc:
        log_event(stage,'failed',error=type(exc).__name__);raise
    log_event(stage,'completed',code=result.returncode)
    return result


def log_preflight(output):
    if not LOG_FILE:return
    allowed=('ARCH ','DPKG_ARCH ','OS ','PY_PATH ','PY_VERSION ','SUDO_PATH ','SYSTEMD_VERSION ','DNSMASQ_VERSION ','PKG ','MISSING ')
    facts=[line for line in output.splitlines() if line.startswith(allowed) and len(line)<=200 and re.fullmatch(r'[A-Za-z0-9 ._+~:/()="-]+',line)]
    if not facts:return
    try:
        with open(LOG_FILE,'a',encoding='utf-8') as stream:stream.write(json.dumps({'time':time.strftime('%Y-%m-%dT%H:%M:%S'),'component':'setup','stage':'preflight_facts','facts':facts},ensure_ascii=True)+'\n')
    except OSError:pass


def prepare(directory,root=ROOT):
    root=Path(root);directory=Path(directory);service_root=root/'app/services'
    manifest=json.loads((root/'firmware/manifest.json').read_text(encoding='utf-8'))
    spec=manifest.get('gateway_appliance') or {};names=spec.get('files');version=spec.get('minimum_python')
    if spec.get('module')!='tools.flight_link.appliance' or not isinstance(names,list) or set(names)!={'tools/flight_link/appliance.py','tools/flight_link/compat_decoder.py'} or version!=[3,4]:
        raise SetupError('网关服务发布清单尚未准备完成')
    expected=manifest.get('service_files_sha256') or {};files={};base=service_root.resolve()
    for name in names:
        source=(service_root/name).resolve()
        if not source.is_relative_to(base):raise SetupError('服务文件路径无效')
        if name not in expected or not source.is_file():raise SetupError('网关服务尚未发布，请先更新完整交付包')
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=expected[name]:raise SetupError('网关服务校验未通过，请更新完整交付包')
        target=directory/'services'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target);files[name]=digest
    digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    meta={'schema':'ann.gateway.package.v1','minimum_python':version,'files':files,'package_sha256':digest}
    (directory/'service.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    shutil.copyfile(root/'app/gateway_setup/linux_installer.py',directory/'linux_installer.py')
    return meta


def ssh_target(user,host):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',user):raise SetupError('SSH 用户名格式无效')
    host=str(ipaddress.IPv4Address(host))
    return user+'@'+host


def choose_remote_interface(output,host,ask=input):
    connection=None;choices=[]
    for line in output.splitlines():
        fields=line.split()
        if len(fields)==5 and fields[0]=='CONNECTION':connection=fields[3]
        elif len(fields)==3 and fields[0]=='ADDRESS' and re.fullmatch(r'[A-Za-z0-9_.-]{1,15}',fields[1]):
            try:address=str(ipaddress.IPv4Interface(fields[2]).ip)
            except ValueError:continue
            choices.append((fields[1],address))
    host=str(ipaddress.IPv4Address(host))
    matches=sorted(set(name for name,address in choices if address==host and address==connection))
    if len(matches)==1:
        print('已识别网关连接网口：'+matches[0],flush=True);return matches[0]
    if not choices:raise SetupError('无法识别网关有地址的有线网口，请检查连接。')
    choices=sorted(set(choices))
    print('检测到多个可能的网关网口，请选择网线直连电脑的网口：')
    for index,(name,address) in enumerate(choices,1):print('  {}. {}（地址 {}）'.format(index,name,address))
    answer=ask('输入序号：').strip()
    if not answer.isdigit() or not 1<=int(answer)<=len(choices):raise SetupError('未选择有效网口')
    return choices[int(answer)-1][0]


PREFLIGHT = r'''PATH=/usr/sbin:/usr/bin:/sbin:/bin:$PATH; export PATH
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
for p in /sys/class/net/*; do n=${p##*/}; [ "$n" = lo ] && continue; [ -d "$p/wireless" ] && continue; [ "$(cat "$p/type")" = 1 ] || continue; ip -o -4 addr show dev "$n" | awk -v n="$n" '{print "ADDRESS " n " " $4}'; done'''


def parse_preflight(output,action='install'):
    rows=output.splitlines();missing=[x[8:] for x in rows if x.startswith('MISSING ')]
    if action=='rollback':missing=[x for x in missing if x!='dnsmasq']
    paths=[x[8:] for x in rows if x.startswith('PY_PATH ')]
    sudo=[x[10:] for x in rows if x.startswith('SUDO_PATH ')]
    if missing:raise SetupError('网关缺少或不兼容所需组件：'+', '.join(missing)+'。未上传文件，也未更改网关；请联系技术支持。')
    if 'PY_OK' not in rows or len(paths)!=1 or not re.fullmatch(r'/[A-Za-z0-9_./+-]+',paths[0]) or len(sudo)!=1 or not re.fullmatch(r'/[A-Za-z0-9_./+-]+',sudo[0]):
        raise SetupError('无法确认网关 Python 版本及路径；未上传文件，也未更改网关。')
    return paths[0],sudo[0]


def package_bytes(directory):
    stream=io.BytesIO()
    with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode='w') as tar:
            for path in sorted(directory.rglob('*')):
                if path.is_file():
                    info=tar.gettarinfo(str(path),arcname=path.relative_to(directory).as_posix());info.mtime=0
                    with path.open('rb') as source:tar.addfile(info,source)
    return stream.getvalue()


def stream_session(args,launcher=subprocess.Popen):
    log_event('ssh_session','started')
    try:
        proc=launcher(args,stdout=subprocess.PIPE,universal_newlines=True,encoding='utf-8',errors='replace')
        pending=''
        while True:
            ch=proc.stdout.read(1)
            if not ch:break
            sys.stdout.write(ch);sys.stdout.flush()
            if ch=='\n':
                log_preflight(pending.rstrip('\r'));pending=''
            elif len(pending)<512:pending+=ch
        if pending:log_preflight(pending.rstrip('\r'))
        code=proc.wait()
        log_event('ssh_session','completed' if code==0 else 'failed',code=code)
        if code:raise subprocess.CalledProcessError(code,args)
    except OSError as exc:
        log_event('ssh_session','failed',error=type(exc).__name__);raise


def remote_exec(user,host,action,interface,eui,launcher=subprocess.Popen):
    target=ssh_target(user,host)
    if action not in ('install','rollback'):raise SetupError('unknown action')
    if interface is not None and (not isinstance(interface,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}',interface)):raise SetupError('网口名格式无效')
    if not re.fullmatch(r'[0-9a-f]{16}',eui):raise SetupError('网关标识格式无效')
    token=uuid.uuid4().hex;remote='/tmp/ann-gateway-'+token
    with tempfile.TemporaryDirectory(prefix='ann-gateway-') as tmp:
        directory=Path(tmp)/'package';directory.mkdir()
        if action=='install':prepare(directory)
        else:shutil.copyfile(ROOT/'app/gateway_setup/linux_installer.py',directory/'linux_installer.py')
        payload=base64.b64encode(package_bytes(directory)).decode('ascii')
        ignore=" | grep -v '^MISSING dnsmasq$'" if action=='rollback' else ''
        select='iface='+interface if interface else "set -- $SSH_CONNECTION; server=$3; iface=$(printf '%s\\n' \"$facts\" | awk -v h='{host}' -v s=\"$server\" '$1==\"ADDRESS\" {{split($3,a,\"/\"); if(a[1]==h && a[1]==s) print $2}}' | sort -u); [ \"$(printf '%s\\n' \"$iface\" | grep -c .)\" = 1 ] || {{ echo '无法唯一确认网关专用网口，未更改网关'; exit 22; }}".format(host=host)
        command="""facts=$({preflight})
printf '%s\\n' "$facts"
missing=$(printf '%s\\n' "$facts" | grep '^MISSING ' {ignore} || true)
[ -z "$missing" ] || {{ echo '缺少网关运行组件，未安装；请将诊断日志交给技术支持'; exit 20; }}
py=$(printf '%s\\n' "$facts" | sed -n 's/^PY_PATH //p'); sudo_path=$(printf '%s\\n' "$facts" | sed -n 's/^SUDO_PATH //p')
printf '%s\\n' "$facts" | grep -qx PY_OK || {{ echo 'Python版本或依赖不兼容，未安装'; exit 20; }}
printf '%s\\n' "$py" "$sudo_path" | grep -Eqv '^/[A-Za-z0-9_./+-]+$' && {{ echo '运行程序路径无效，未安装'; exit 20; }}
[ -n "$py" ] && [ -n "$sudo_path" ] || exit 20
{select}
echo '网关环境检查通过，正在安装；如要求管理员密码，请输入后按回车。'
set -e; mkdir -m 700 {r}; trap 'rm -rf {r}' EXIT; printf '%s' '{payload}' | base64 -d | tar -xzm -C {r}
"$sudo_path" "$py" {r}/linux_installer.py {action}{extra}
""".format(preflight=PREFLIGHT,ignore=ignore,select=select,r=remote,payload=payload,action=action,extra=(' --package '+remote+' --interface "$iface" --gateway-eui '+eui+' --dedicated') if action=='install' else '')
        if len(command)>28000:raise SetupError('交付包过大，无法安全传送；未更改网关。')
        print('正在连接网关。若提示输入密码，输入时屏幕不会显示字符，输完按回车。',flush=True)
        stream_session(['ssh']+SSH_OPTIONS+['-tt',target,command],launcher)


def main():
    global LOG_FILE
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=['install','rollback'],default='install');p.add_argument('--host',default='192.168.137.200')
    p.add_argument('--user',default='rxhf');p.add_argument('--interface');p.add_argument('--gateway-eui',default='b827ebfffe32e2c1')
    p.add_argument('--plan',action='store_true',help='validate delivery files without network or changes')
    p.add_argument('--log-file',help=argparse.SUPPRESS)
    a=p.parse_args()
    LOG_FILE=a.log_file
    try:
        ssh_target(a.user,a.host)
        if a.plan:
            with tempfile.TemporaryDirectory(prefix='ann-gateway-plan-') as tmp:
                meta=prepare(tmp);print(json.dumps({'status':'ready_for_review','minimum_python':meta['minimum_python'],'hardware_access':False}))
            return 0
        remote_exec(a.user,a.host,a.action,a.interface,a.gateway_eui);return 0
    except (SetupError,OSError,ValueError,EOFError,subprocess.CalledProcessError) as exc:
        log_event('setup','failed',code=exc.returncode if isinstance(exc,subprocess.CalledProcessError) else None,error=type(exc).__name__)
        if isinstance(exc,subprocess.CalledProcessError):
            print('未完成：连接或远端操作失败（退出码 {}），请检查上方提示及诊断日志。'.format(exc.returncode),file=sys.stderr)
        else:print('未完成：'+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())

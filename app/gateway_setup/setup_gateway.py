"""Create a verified gateway package and run interactive OpenSSH; no passwords are saved."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[2]
class SetupError(RuntimeError):pass


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


def remote_exec(user,host,action,interface,eui,runner=subprocess.run):
    target=ssh_target(user,host)
    if action not in ('install','rollback'):raise SetupError('unknown action')
    if action=='install' and interface is None:
        print('正在连接网关。若提示输入密码，输入时屏幕不会显示字符，输完按回车。',flush=True)
        command='printf "CONNECTION %s\\n" "$SSH_CONNECTION"; for p in /sys/class/net/*; do n=${p##*/}; [ "$n" = lo ] && continue; [ -d "$p/wireless" ] && continue; [ "$(cat "$p/type")" = 1 ] || continue; ip -o -4 addr show dev "$n" | awk -v n="$n" \'{print "ADDRESS " n " " $4}\'; done'
        found=runner(['ssh',target,command],check=True,stdout=subprocess.PIPE,universal_newlines=True)
        interface=choose_remote_interface(found.stdout,host)
    if action=='install' and (not isinstance(interface,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}',interface)):raise SetupError('网口名格式无效')
    if not re.fullmatch(r'[0-9a-f]{16}',eui):raise SetupError('网关标识格式无效')
    token=uuid.uuid4().hex;remote='/tmp/ann-gateway-'+token
    with tempfile.TemporaryDirectory(prefix='ann-gateway-') as tmp:
        directory=Path(tmp)/'package';directory.mkdir()
        if action=='install':prepare(directory)
        else:shutil.copyfile(ROOT/'app/gateway_setup/linux_installer.py',directory/'linux_installer.py')
        archive=Path(tmp)/'package.tar.gz'
        with tarfile.open(str(archive),'w:gz') as tar:
            for path in sorted(directory.rglob('*')):
                if path.is_file():tar.add(str(path),arcname=path.relative_to(directory).as_posix(),recursive=False)
        print('请按提示输入网关密码；输入时不会显示字符，输完按回车。密码不会被保存。',flush=True)
        runner(['scp',str(archive),target+':'+remote+'.tar.gz'],check=True)
        command='mkdir -m 700 {r} && tar -xzf {r}.tar.gz -C {r} && sudo python3 {r}/linux_installer.py {action}'.format(r=remote,action=action)
        if action=='install':command+=' --package '+remote+' --interface '+interface+' --gateway-eui '+eui+' --dedicated'
        runner(['ssh','-tt',target,command],check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=['install','rollback'],default='install');p.add_argument('--host',default='192.168.137.200')
    p.add_argument('--user',default='rxhf');p.add_argument('--interface');p.add_argument('--gateway-eui',default='b827ebfffe32e2c1')
    p.add_argument('--plan',action='store_true',help='validate delivery files without network or changes')
    a=p.parse_args()
    try:
        ssh_target(a.user,a.host)
        if a.plan:
            with tempfile.TemporaryDirectory(prefix='ann-gateway-plan-') as tmp:
                meta=prepare(tmp);print(json.dumps({'status':'ready_for_review','minimum_python':meta['minimum_python'],'hardware_access':False}))
            return 0
        remote_exec(a.user,a.host,a.action,a.interface,a.gateway_eui);return 0
    except (SetupError,OSError,ValueError,subprocess.CalledProcessError) as exc:
        print('未完成：'+str(exc),file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())

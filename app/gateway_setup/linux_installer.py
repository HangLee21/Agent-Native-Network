#!/usr/bin/env python3
"""Install/rollback the dedicated gateway appliance. Never run without explicit action."""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

STATE='/var/lib/ann-gateway'
SERVICE='/etc/systemd/system/ann-gateway.service'
DHCP='/etc/systemd/system/ann-gateway-dhcp.service'
ADDRESS='/etc/systemd/system/ann-gateway-address.service'
HTTP_SOCKET='/etc/systemd/system/ann-gateway-http.socket'
DISCOVERY_SOCKET='/etc/systemd/system/ann-gateway-discovery.socket'
DHCP_CONF='/etc/ann-gateway/dnsmasq.conf'
LOCAL_CONF='/opt/risinghf/pktfwd/local_conf.json'
RELEASE='/opt/ann-gateway/release'
SYS_NET='/sys/class/net'
SYSTEMD_DIR='/etc/systemd/system'
PATHS=[SERVICE,DHCP,ADDRESS,HTTP_SOCKET,DISCOVERY_SOCKET,DHCP_CONF,LOCAL_CONF]
UNITS=('ann-gateway-address.service','ann-gateway-dhcp.service','ann-gateway-http.socket','ann-gateway-discovery.socket','ann-gateway.service')


class SetupError(RuntimeError): pass


def read_bytes(path):
    with open(str(path),'rb') as stream:return stream.read()


def read_text(path):
    return read_bytes(path).decode('utf-8')


def mkdirp(path):
    try:os.makedirs(str(path))
    except OSError:
        if not os.path.isdir(str(path)):raise


def configuration(interface,address,cidr,pool_start,pool_end,eui):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}',interface):raise SetupError('invalid interface')
    if not re.fullmatch(r'[0-9a-f]{16}',eui):raise SetupError('invalid gateway EUI')
    network=ipaddress.ip_network(cidr,strict=True);ip=ipaddress.ip_address(address)
    start=ipaddress.ip_address(pool_start);end=ipaddress.ip_address(pool_end)
    if network.version!=4 or network.prefixlen>29 or ip not in network or start not in network or end not in network:
        raise SetupError('address and pool must be in an IPv4 subnet')
    if int(start)>int(end) or int(start)<=int(ip)<=int(end) or start==network.network_address or end==network.broadcast_address or ip in (network.network_address,network.broadcast_address):
        raise SetupError('pool overlaps gateway or reserved network addresses')
    if not network.is_private:raise SetupError('dedicated private IPv4 subnet required')
    dns='\n'.join(['port=0','interface='+interface,'bind-interfaces','dhcp-authoritative',
        'user=nobody','group=nogroup','dhcp-leasefile=/var/lib/ann-gateway/state/dnsmasq.leases',
        'dhcp-range='+str(start)+','+str(end)+','+str(network.netmask)+',12h',
        'dhcp-option=3','dhcp-option=6',''])
    return dict(interface=interface,address=str(ip),network=str(network),prefix=network.prefixlen,
                pool_start=str(start),pool_end=str(end),gateway_eui=eui,dnsmasq=dns)


def render_units(c,python,dnsmasq='/usr/sbin/dnsmasq'):
    service='''[Unit]\nDescription=AD-HOC gateway local receiver\nRequires=ann-gateway-http.socket ann-gateway-discovery.socket\nAfter=ann-gateway-http.socket ann-gateway-discovery.socket\n[Service]\nType=simple\nUser=nobody\nSockets=ann-gateway-http.socket ann-gateway-discovery.socket\nEnvironment=PYTHONPATH=/opt/ann-gateway/release\nExecStart={python} -B -m tools.flight_link.appliance --gateway-eui {eui} --forwarder-host 127.0.0.1 --forwarder-port 1680 --http-host {ip} --http-port 8780 --discovery-host 0.0.0.0 --discovery-port 8781 --interface {interface} --systemd-sockets\nRestart=on-failure\nRestartSec=5\nProtectSystem=full\nReadWriteDirectories=/var/lib/ann-gateway/state\nStandardOutput=null\nStandardError=null\n[Install]\nWantedBy=multi-user.target\n'''.format(python=python,eui=c['gateway_eui'],ip=c['address'],interface=c['interface'])
    address='''[Unit]\nDescription=Dedicated gateway address\nAfter=network.target\n[Service]\nType=oneshot\nExecStart=/sbin/ip address replace {ip}/{prefix} dev {interface}\nRemainAfterExit=yes\n[Install]\nWantedBy=multi-user.target\n'''.format(ip=c['address'],prefix=c['prefix'],interface=c['interface'])
    dhcp='''[Unit]\nDescription=Dedicated gateway DHCP\nRequires=ann-gateway-address.service\nAfter=ann-gateway-address.service\n[Service]\nType=simple\nExecStart={dnsmasq} --keep-in-foreground --log-facility=/dev/null --conf-file=/etc/ann-gateway/dnsmasq.conf\nRestart=on-failure\nRestartSec=5\nStandardOutput=null\nStandardError=null\n[Install]\nWantedBy=multi-user.target\n'''.format(dnsmasq=dnsmasq)
    http='''[Unit]\nDescription=Dedicated gateway HTTP socket\nRequires=ann-gateway-address.service\nAfter=ann-gateway-address.service\n[Socket]\nListenStream={ip}:8780\nBindToDevice={interface}\nService=ann-gateway.service\n[Install]\nWantedBy=sockets.target\n'''.format(ip=c['address'],interface=c['interface'])
    discovery='''[Unit]\nDescription=Dedicated gateway discovery socket\nRequires=ann-gateway-address.service\nAfter=ann-gateway-address.service\n[Socket]\nListenDatagram=0.0.0.0:8781\nBindToDevice={interface}\nService=ann-gateway.service\n[Install]\nWantedBy=sockets.target\n'''.format(interface=c['interface'])
    return {SERVICE:service,DHCP:dhcp,ADDRESS:address,HTTP_SOCKET:http,DISCOVERY_SOCKET:discovery,DHCP_CONF:c['dnsmasq']}


def capture(path):
    p=Path(path)
    if p.is_symlink():return {'type':'symlink','target':os.readlink(str(p))}
    if not p.exists():return {'type':'absent'}
    if not p.is_file():raise SetupError('unexpected non-file: '+str(p))
    stat=p.stat();return {'type':'file','data':base64.b64encode(read_bytes(p)).decode('ascii'),
        'mode':stat.st_mode & 0o7777,'uid':stat.st_uid,'gid':stat.st_gid}


def write_atomic(path,data,mode=0o644):
    p=Path(path);mkdirp(p.parent)
    fd,tmp=tempfile.mkstemp(prefix='.ann-',dir=str(p.parent))
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(tmp,mode);os.replace(tmp,str(p))
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def restore(path,snapshot):
    p=Path(path);kind=snapshot['type']
    if kind=='absent':
        if p.is_file() or p.is_symlink():p.unlink()
    elif kind=='symlink':
        if p.exists() or p.is_symlink():p.unlink()
        mkdirp(p.parent);p.symlink_to(snapshot['target'])
    elif kind=='file':
        write_atomic(p,base64.b64decode(snapshot['data']),snapshot['mode'])
        os.chown(str(p),snapshot['uid'],snapshot['gid'])
    else:raise SetupError('invalid backup type')


def call(*args,check=True):
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
    stdout,stderr=process.communicate()
    if check and process.returncode:raise SetupError('command failed: '+args[0]+': '+stderr.strip())
    class Result:pass
    result=Result();result.stdout=stdout;result.stderr=stderr;result.returncode=process.returncode
    return result


def current_service(name):
    return {'enabled':call('systemctl','is-enabled',name,check=False).stdout.strip(),
            'active':call('systemctl','is-active',name,check=False).stdout.strip()}


def check_ports():
    sockets=[]
    try:
        for kind,port,address in ((socket.SOCK_DGRAM,67,'0.0.0.0'),(socket.SOCK_DGRAM,1680,'127.0.0.1'),
                                  (socket.SOCK_STREAM,8780,'0.0.0.0'),(socket.SOCK_DGRAM,8781,'0.0.0.0')):
            wire=socket.socket(socket.AF_INET,kind);sockets.append(wire)
            wire.bind((address,port))
    except OSError as exc:raise SetupError('网关服务端口已被占用，未修改配置：'+str(exc))
    finally:
        for wire in sockets:wire.close()


def verify_package(package):
    package=Path(package).resolve();meta=json.loads(read_text(package/'service.json'))
    if meta.get('schema')!='ann.gateway.package.v1' or not isinstance(meta.get('files'),dict) or not meta['files']:
        raise SetupError('invalid service package')
    service_root=(package/'services').resolve()
    present=set()
    for item in service_root.rglob('*'):
        if item.is_symlink():raise SetupError('service package contains a symlink')
        if item.is_file():present.add(item.relative_to(service_root).as_posix())
    if present!=set(meta['files']):raise SetupError('service package has missing or unexpected files')
    for rel,digest in meta['files'].items():
        path=(package/'services'/rel).resolve()
        try:path.relative_to((package/'services').resolve())
        except ValueError:raise SetupError('service path escapes package')
        if not path.is_file() or hashlib.sha256(read_bytes(path)).hexdigest()!=digest:
            raise SetupError('service package hash mismatch: '+rel)
    digest=hashlib.sha256(json.dumps(meta['files'],sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    if meta.get('package_sha256')!=digest:raise SetupError('service package manifest mismatch')
    version=meta.get('minimum_python')
    if not isinstance(version,list) or len(version)!=2 or any(type(x) is not int or x<0 for x in version):raise SetupError('service minimum Python not declared')
    return meta


def verify_service(config):
    # A device-bound socket may reject local loopback connections. Verify
    # process/socket activation here; the PC verifies API identity afterward.
    for unit in ('ann-gateway-http.socket','ann-gateway-discovery.socket','ann-gateway.service'):
        if current_service(unit)['active']!='active':raise SetupError('网关服务未就绪：'+unit)


def rollback():
    saved=Path(STATE)/'backup.json'
    if not saved.is_file():raise SetupError('no installation backup')
    state=json.loads(read_text(saved))
    if state.get('phase')!='rolling_back':
        state['phase']='rolling_back'
        write_atomic(saved,json.dumps(state,indent=2).encode('utf-8'),0o600)
    failures=[]
    for unit in reversed(UNITS):
        load=call('systemctl','show','--property=LoadState',unit,check=False)
        if load.returncode==0 and load.stdout.strip()=='LoadState=not-found':continue
        for action in ('stop','disable'):
            result=call('systemctl',action,unit,check=False)
            if result.returncode:failures.append(unit+' '+action+': '+result.stderr.strip())
        active=call('systemctl','is-active',unit,check=False)
        enabled=call('systemctl','is-enabled',unit,check=False)
        if active.stdout.strip() not in ('inactive','failed','unknown'):failures.append(unit+' remains active: '+active.stdout.strip())
        if enabled.stdout.strip() not in ('disabled','not-found'):failures.append(unit+' remains enabled: '+enabled.stdout.strip())
    if failures:raise SetupError('回滚未完成，恢复记录已保留：'+'; '.join(failures))
    for path,snapshot in state['files'].items():restore(path,snapshot)
    if not state['address_was_present']:
        c=state['config'];address=c['address']+'/'+str(c['prefix'])
        before=call('ip','-o','-4','addr','show','dev',c['interface'],check=False)
        if before.returncode:raise SetupError('无法检查网口地址，恢复记录已保留：'+before.stderr.strip())
        if address in before.stdout:
            result=call('/sbin/ip','address','del',address,'dev',c['interface'],check=False)
            if result.returncode:raise SetupError('删除网关地址失败，恢复记录已保留：'+result.stderr.strip())
            after=call('ip','-o','-4','addr','show','dev',c['interface'],check=False)
            if after.returncode or address in after.stdout:raise SetupError('网关地址尚未移除，恢复记录已保留')
    call('systemctl','daemon-reload')
    original=state['pktfwd']
    if original['enabled']=='enabled':call('systemctl','enable','pktfwd.service')
    elif original['enabled']=='disabled':call('systemctl','disable','pktfwd.service')
    if original['active']=='active':call('systemctl','restart','pktfwd.service')
    else:call('systemctl','stop','pktfwd.service')
    restored=current_service('pktfwd.service')
    if original['enabled'] in ('enabled','disabled') and restored['enabled']!=original['enabled']:
        raise SetupError('转发服务启用状态未恢复，恢复记录已保留')
    if (restored['active']=='active') != (original['active']=='active'):
        raise SetupError('转发服务运行状态未恢复，恢复记录已保留')
    release=Path(RELEASE)
    if release.is_dir():
        expected=state.get('package_files',{})
        existing=[p for p in release.rglob('*') if p.is_file() or p.is_symlink()]
        safe=all(not p.is_symlink() and p.relative_to(release).as_posix() in expected and hashlib.sha256(read_bytes(p)).hexdigest()==expected[p.relative_to(release).as_posix()] for p in existing)
        if safe:shutil.rmtree(str(release))
        else:print('服务目录包含额外或变更文件，已保留。')
    saved.rename(saved.with_name('backup-restored-'+uuid.uuid4().hex+'.json'))
    print('原转发配置和服务状态已恢复；备份及运行数据保留。')


def install(package,c,python_executable=None,dnsmasq_executable=None,dedicated=False):
    if not dedicated:raise SetupError('必须明确确认专用网口，未修改配置')
    if os.geteuid()!=0:raise SetupError('需要管理员权限')
    meta=verify_package(package)
    if sys.version_info<tuple(meta['minimum_python']):raise SetupError('网关 Python 版本不满足服务要求；未修改任何配置')
    python_executable=python_executable or sys.executable
    dnsmasq_executable=dnsmasq_executable or '/usr/sbin/dnsmasq'
    private='/opt/ann-gateway/runtime/jessie-armhf-v1/bin/'
    if python_executable!=sys.executable and python_executable!=private+'python3':raise SetupError('invalid Python wrapper')
    if dnsmasq_executable not in ('/usr/sbin/dnsmasq',private+'dnsmasq'):raise SetupError('invalid dnsmasq wrapper')
    for command in ('systemctl','ip'):
        if not shutil.which(command):raise SetupError('缺少依赖: '+command)
    if dnsmasq_executable=='/usr/sbin/dnsmasq' and not shutil.which('dnsmasq'):raise SetupError('缺少依赖: dnsmasq')
    if dnsmasq_executable!= '/usr/sbin/dnsmasq' and not os.access(dnsmasq_executable,os.X_OK):raise SetupError('私有 DHCP 程序不可执行')
    try:
        import pwd,grp
        owner=pwd.getpwnam('nobody');lease_group=grp.getgrnam('nogroup')
    except (ImportError,KeyError):raise SetupError('网关缺少 nobody 用户或 nogroup 用户组，未修改配置')
    iface=Path(SYS_NET)/c['interface']
    if not iface.exists() or (iface/'wireless').exists() or read_text(iface/'type').strip()!='1':raise SetupError('请选择已连接的专用有线接口')
    original_default_route=call('ip','route','show','default','dev',c['interface']).stdout.strip()
    if original_default_route:print('专用网口已有默认路由，将保留原配置：'+original_default_route)
    if call('systemctl','is-active','dnsmasq.service',check=False).stdout.strip()=='active':raise SetupError('已有 DHCP 服务运行，未修改')
    saved=Path(STATE)/'backup.json'
    if saved.exists():
        current=json.loads(read_text(saved))
        if current.get('phase')!='installed':
            print('检测到未完成的安装，先恢复原配置。')
            rollback()
        elif current['config']==c and current.get('package_hash')==meta['package_sha256']:
            for unit in UNITS:
                if current_service(unit)['active']!='active':call('systemctl','start',unit)
            verify_service(c)
            print('该配置已安装；服务已检查。');return
        else:raise SetupError('已有安装，请先回滚或使用相同配置')
    for unit in UNITS:
        if Path(SYSTEMD_DIR,unit).exists():raise SetupError('已有同名服务，避免覆盖')
    if Path(RELEASE).exists():raise SetupError('服务目录已存在，避免覆盖')
    check_ports()
    original=capture(LOCAL_CONF)
    try:conf=json.loads(read_text(LOCAL_CONF))
    except Exception as exc:raise SetupError('无法读取现有转发器配置') from exc
    gw=conf.get('gateway_conf')
    if not isinstance(gw,dict) or str(gw.get('gateway_ID','')).lower()!=c['gateway_eui']:
        raise SetupError('网关 EUI 与现有转发器配置不匹配')
    gw.update(server_address='127.0.0.1',serv_port_up=1680,serv_port_down=1680)
    units=render_units(c,python_executable,dnsmasq_executable)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',delete=False) as f:
        f.write(c['dnsmasq']);tmp=f.name
    try:call(dnsmasq_executable,'--test','--conf-file='+tmp)
    finally:os.unlink(tmp)
    addr=call('ip','-o','-4','addr','show','dev',c['interface']).stdout
    present=(c['address']+'/'+str(c['prefix'])) in addr
    state={'schema':1,'config':c,'files':{p:capture(p) for p in PATHS},'pktfwd':current_service('pktfwd.service'),
           'address_was_present':present,'original_default_route':original_default_route,'package_hash':meta['package_sha256'],'package_files':meta['files'],'phase':'installing'}
    write_atomic(saved,json.dumps(state,indent=2).encode('utf-8'),0o600)
    try:
        mkdirp(Path(RELEASE).parent)
        shutil.copytree(str(Path(package)/'services'),RELEASE)
        for rel,digest in meta['files'].items():
            if hashlib.sha256(read_bytes(Path(RELEASE)/rel)).hexdigest()!=digest:raise SetupError('copied service checksum mismatch')
        import_check=os.environ.copy();import_check['PYTHONPATH']=RELEASE
        child=subprocess.Popen([python_executable,'-B','-c','import tools.flight_link.appliance'],env=import_check)
        if child.wait()!=0:raise SetupError('网关服务依赖检查失败')
        writable=Path(STATE)/'state';mkdirp(writable);os.chown(str(writable),owner.pw_uid,lease_group.gr_gid);os.chmod(str(writable),0o750)
        write_atomic(LOCAL_CONF,(json.dumps(conf,indent=2)+'\n').encode('utf-8'))
        for path,content in units.items():write_atomic(path,content.encode('utf-8'))
        call('systemctl','daemon-reload')
        for unit in UNITS:
            call('systemctl','enable',unit);call('systemctl','start',unit)
        verify_service(c)
        call('systemctl','restart','pktfwd.service')
        state['phase']='installed'
        write_atomic(saved,json.dumps(state,indent=2).encode('utf-8'),0o600)
        print('安装完成：请重新连接电脑网线，等待自动获取地址。')
    except Exception:
        rollback()
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','install','rollback'])
    p.add_argument('--package');p.add_argument('--interface',default='eth0');p.add_argument('--address',default='192.168.137.200')
    p.add_argument('--network',default='192.168.137.0/24');p.add_argument('--pool-start',default='192.168.137.20');p.add_argument('--pool-end',default='192.168.137.99')
    p.add_argument('--gateway-eui',default='b827ebfffe32e2c1');p.add_argument('--dedicated',action='store_true')
    p.add_argument('--python-wrapper');p.add_argument('--dnsmasq-wrapper')
    a=p.parse_args()
    try:
        if a.action=='rollback':rollback();return 0
        c=configuration(a.interface,a.address,a.network,a.pool_start,a.pool_end,a.gateway_eui)
        if a.action=='plan':print(json.dumps({'config':c,'units':render_units(c,'/usr/bin/python3')},indent=2));return 0
        if not a.dedicated or not a.package:raise SetupError('必须明确确认专用网口并提供完整服务包')
        install(a.package,c,a.python_wrapper,a.dnsmasq_wrapper,dedicated=a.dedicated);return 0
    except Exception as exc:print('未完成：'+str(exc),file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())

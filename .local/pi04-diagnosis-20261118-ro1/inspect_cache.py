import os, struct, sys, json, traceback, hashlib, re
from datetime import datetime, timezone
from pathlib import Path
out = {}
def u(buf, at, fmt): return struct.unpack_from('<' + fmt, buf, at)[0]
def raw(offset, size):
    start = offset // 512 * 512
    disk.seek(start)
    data = disk.read(((offset-start+size+511)//512)*512)
    return data[offset-start:offset-start+size]
def collect():
    global disk
    disk=open(r'\\.\PhysicalDrive2','rb',buffering=0)
    m=raw(0,512)
    assert m[-2:]==bytes.fromhex('55aa') and m[466]==0x83
    base=u(m,470,'I')*512
    assert base>536870912 and u(m,474,'I')*512==63319310336, 'card partitions changed'
    s=raw(base+1024,1024)
    assert u(s,56,'H')==0xef53
    block=1024<<u(s,24,'I')
    desc=max(32,u(s,254,'H')); ips=u(s,40,'I'); inode_size=u(s,88,'H')
    out['ext4']={'volume_label':s[120:136].split(b'\0')[0].decode(errors='replace'),'last_mount_utc':datetime.fromtimestamp(u(s,44,'I'),timezone.utc).isoformat(),'mount_count':u(s,52,'H')}
    def inode(n):
        group,idx=divmod(n-1,ips)
        g=raw(base+(u(s,20,'I')+1)*block+group*desc,desc)
        table=u(g,8,'I')+((u(g,40,'I')<<32) if desc>=64 else 0)
        return raw(base+table*block+idx*inode_size,inode_size)
    def runs(b):
        assert u(b,0,'H')==0xf30a
        for i in range(u(b,2,'H')):
            at=12+12*i
            if u(b,6,'H'):
                child=u(b,at+4,'I')+(u(b,at+8,'H')<<32)
                yield from runs(raw(base+child*block,block))
            else:
                length=u(b,at+4,'H')
                if length<=32768: yield u(b,at,'I')*block,length*block,(u(b,at+6,'H')*2**32+u(b,at+8,'I'))*block
    def data(n,cap,tail=False):
        b=inode(n); size=u(b,4,'I')+(u(b,108,'I')<<32); start=max(0,size-cap) if tail else 0
        result=bytearray(min(size,cap))
        if result:
            for pos,length,physical in runs(b[40:100]):
                a=max(start,pos);z=min(start+len(result),pos+length)
                if z>a:result[a-start:z-start]=raw(base+physical+a-pos,z-a)
        return bytes(result)
    def children(n):
        b=data(n,4*1024*1024); d={};at=0
        while at+8<=len(b):
            ino,span,nlen,_=struct.unpack_from('<IHBB',b,at)
            if span<8:break
            if ino:d[b[at+8:at+8+nlen].decode(errors='replace')]=ino
            at+=span
        return d
    def find(p):
        n=2
        for part in p.strip('/').split('/'):
            n=children(n).get(part)
            if not n:return None
        return n
    paths=['/etc/cloud/cloud-init.disabled','/usr/bin/cloud-init','/var/lib/cloud/instance','/var/lib/cloud/data/instance-id','/var/lib/cloud/data/status.json','/var/lib/cloud/instances','/var/log/cloud-init.log','/var/log/cloud-init-output.log','/var/log/journal','/etc/systemd/system/eora-firstboot.service','/usr/local/sbin/eora-firstboot-logic.sh','/var/log/eora-firstboot.log']
    out['present']={p:bool(find(p)) for p in paths}
    for path in ['/var/log/cloud-init.log','/var/log/cloud-init-output.log','/var/log/syslog']:
        n=find(path)
        if n:
            t=data(n,1500000,True).decode(errors='replace').lower()
            out[path]={k:t.count(k) for k in ['datasourcenocloud','eora-firstboot','running module runcmd','scripts-user','cloud-init.disabled','failed','error','traceback','network-config']}
    n=find('/var/lib/cloud/instances')
    if n:
        out['instance_types']=['imager' if k.startswith('rpi-imager') else 'eora' if k.startswith('eora-') else 'other' for k in children(n) if k not in ('.','..')]
    n=find('/etc/os-release') or find('/usr/lib/os-release')
    n=find('/usr/lib/os-release')
    if n:
        out['release']=next((l for l in data(n,4096).decode(errors='replace').splitlines() if l.startswith('PRETTY_NAME=')),None)
    n=find('/etc/hostname')
    if n:out['hostname_is_04']=data(n,128).strip()==b'eora-air-04'
    n=find('/var/lib/cloud/data/status.json')
    if n:
        state=json.loads(data(n,200000)).get('v1',{})
        out['cloud_stages']={k:{'start':v.get('start'),'finished':v.get('finished'),'error_count':len(v.get('errors',[]))} for k,v in state.items() if isinstance(v,dict) and 'start' in v}
    cache=data(find('/var/lib/cloud/data/instance-id'),512).decode().strip()
    boot=Path('F:/')
    cli=re.search(r'ds=nocloud;i=([^\s;]+)',(boot/'cmdline.txt').read_text()).group(1)
    meta=re.search(r'instance-id:\s*([^\s]+)',(boot/'meta-data').read_text()).group(1)
    out['cached_id_matches_cmdline']=cache==cli
    out['cached_id_matches_meta']=cache==meta
    inst='/var/lib/cloud/instances/'+cache+'/'
    for name in ('user-data.txt','scripts/runcmd','sem/config_runcmd','sem/config_scripts_user'):
        n=find(inst+name)
        out[name]={'present':bool(n),'contains_eora_installer':bool(n and b'eora-firstboot.sh' in data(n,80000))}
    n=find('/var/log/cloud-init-output.log')
    if n:
        t=data(n,300000,True).decode(errors='replace')
        for keyword in ['failed to fetch','temporary failure resolving','network is unreachable','could not resolve','failed to connect','failed to start','802.1x','wlan0','package','systemctl','ssh.service']:
            out.setdefault('output_keywords',{})[keyword]=t.lower().count(keyword)
    n=find('/etc/NetworkManager/system-connections')
    if n:
        out['saved_wifi_eap_profiles']=sum(1 for k,i in children(n).items() if k.endswith('.nmconnection') and b'[802-1x]' in data(i,60000))
try:collect()
except Exception as e:out['diagnostic_error']=type(e).__name__+': '+str(e)[:180];out['line']=traceback.extract_tb(e.__traceback__)[-1].lineno
with Path(__file__).with_name('cache-observations.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)

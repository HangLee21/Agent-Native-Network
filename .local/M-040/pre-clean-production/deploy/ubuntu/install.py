"""Install or stage exact-device Ubuntu files. No serial probing or firmware writes."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import hashlib
import sys
ROOT=Path(__file__).resolve().parents[2]
OWNED=('opt/mid-edge','etc/mid-edge','etc/udev/rules.d/99-mid-edge.rules','etc/systemd/system/mid-edge@.service')

def validate(config):
    required={'id_path','interface','vid','pid','node_id','baud','http_port','start_policy'}
    if set(config)!=required:raise ValueError('config must have exactly '+','.join(sorted(required)))
    if not re.fullmatch(r'[A-Za-z0-9_:./-]{8,200}',config['id_path']):raise ValueError('exact registered ID_PATH required, no wildcards')
    for name,size in [('interface',2),('vid',4),('pid',4)]:
        if not re.fullmatch('[0-9a-f]{'+str(size)+'}',config[name]):raise ValueError('lowercase hex '+name+' required')
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',config['node_id']):raise ValueError('registered STA MAC required')
    if type(config['baud']) is not int or config['baud'] not in [115200,460800]:raise ValueError('explicit firmware baud required')
    if type(config['http_port']) is not int or not 1024<=config['http_port']<=65535:raise ValueError('unprivileged localhost HTTP port required')
    if config['start_policy'] not in ['saved','observe']:raise ValueError('start_policy must be saved/observe; provisioning is separate')
    return config

def rule(c):
    validate(c)
    return ('# Exact registered USB slot/interface; VID/PID alone is never sufficient.\n'
        'ACTION=="add|change", SUBSYSTEM=="tty", ENV{ID_PATH}=="'+c['id_path']+'", '
        'ENV{ID_USB_INTERFACE_NUM}=="'+c['interface']+'", ENV{ID_VENDOR_ID}=="'+c['vid']+'", ENV{ID_MODEL_ID}=="'+c['pid']+'", '
        'GROUP="mid-edge", MODE="0660", ENV{ID_MM_DEVICE_IGNORE}="1", ENV{ID_MM_PORT_IGNORE}="1", '
        'TAG+="systemd", ENV{SYSTEMD_WANTS}+="mid-edge@%k.service"\n')

def matches(c,props):
    return all(props.get(k)==c[v] for k,v in [('ID_PATH','id_path'),('ID_USB_INTERFACE_NUM','interface'),('ID_VENDOR_ID','vid'),('ID_MODEL_ID','pid')])

def install(config,root):
    validate(config);root=Path(root).resolve();target=root/'opt/mid-edge'
    if target.exists() and not (target/'.mid-edge-owned').is_file():raise ValueError('refuse replacing unowned /opt/mid-edge')
    for path in OWNED[1:]:
        p=root/path
        if p.exists() and not (target/'.mid-edge-owned').exists():raise ValueError('refuse replacing unowned '+path)
    target.mkdir(parents=True,exist_ok=True);(target/'.mid-edge-owned').write_text('M-027\n')
    for folder,names in [('tools/mid_edge',['__init__.py','client.py','__main__.py','local_api.py','linux_service.py','service_api.py','lora.py','board_service.py','mobile_position.py','README.md','AUTONOMOUS.md']),('tools/mid_sim_console',['local_edge.py'])]:
        dst=target/folder;dst.mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copyfile(ROOT/folder/name,dst/name)
    shutil.copyfile(ROOT/'firmware/mid_baseline/field_agent/lora_ref/decoder.py',target/'tools/mid_edge/_lora_decoder.py')
    shutil.copytree(ROOT/'tools/mid_sim_console/edge_assets',target/'tools/mid_sim_console/edge_assets',dirs_exist_ok=True)
    ui=target/'research/agent_native_network/mid_sim_console';ui.mkdir(parents=True,exist_ok=True)
    for name in ['index.html','workbench.js','sender.js','route-view.js','neighbors.js']:
        p=ROOT/'research/agent_native_network/mid_sim_console'/name
        if p.exists():shutil.copyfile(p,ui/name)
    for rel,data in [('etc/mid-edge/config.json',json.dumps(config,indent=2)+'\n'),('etc/udev/rules.d/99-mid-edge.rules',rule(config)),('etc/systemd/system/mid-edge@.service',(ROOT/'deploy/ubuntu/mid-edge@.service').read_text())]:
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data,encoding='utf-8')
    inventory={str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file() and p.name!='INSTALL_MANIFEST.json'}
    (target/'INSTALL_MANIFEST.json').write_text(json.dumps(dict(schema='mid.edge.ubuntu.install.v1',files_sha256=inventory,config_sha256=hashlib.sha256((root/'etc/mid-edge/config.json').read_bytes()).hexdigest()),indent=2),encoding='utf-8')

def uninstall(root,purge=False):
    root=Path(root).resolve();owner=root/'opt/mid-edge/.mid-edge-owned'
    if not owner.is_file():raise ValueError('no owned installation marker; nothing removed')
    # Fixed paths only. Never follow a caller-selected removal path or symlink.
    for rel in OWNED:
        p=root/rel
        if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('unsafe installed target '+rel)
    if purge:
        state=root/'var/lib/mid-edge'
        if state.is_symlink() or not state.resolve().is_relative_to(root):raise ValueError('unsafe state target')
    for rel in reversed(OWNED):
        p=root/rel
        if p.is_dir():shutil.rmtree(p)
        elif p.exists():p.unlink()
    if purge:
        p=root/'var/lib/mid-edge'
        if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('unsafe state target')
        if p.exists():shutil.rmtree(p)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['install','uninstall']);p.add_argument('--config');p.add_argument('--root',default='/');p.add_argument('--activate',action='store_true');p.add_argument('--purge-state',action='store_true');a=p.parse_args();root=Path(a.root).resolve();live=root==Path(root.anchor)
    if live and (os.name!='posix' or os.geteuid()!=0):p.error('live installation requires Ubuntu root; use --root for staging')
    if a.activate and not live:p.error('--activate only with live root')
    if live and not a.activate:p.error('live install/uninstall requires --activate; use --root to stage without system changes')
    if a.action=='install':
        if not a.config:p.error('--config required')
        config=validate(json.loads(Path(a.config).read_bytes()))
        if a.activate:
            subprocess.run([sys.executable,'-c','import serial'],check=True)
            subprocess.run(['getent','group','mid-edge'],stdout=subprocess.DEVNULL).returncode==0 or subprocess.run(['groupadd','--system','mid-edge'],check=True)
            subprocess.run(['id','-u','mid-edge'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0 or subprocess.run(['useradd','--system','--gid','mid-edge','--home-dir','/var/lib/mid-edge','--shell','/usr/sbin/nologin','mid-edge'],check=True)
        install(config,root)
    elif a.activate:
        if not (root/'opt/mid-edge/.mid-edge-owned').is_file():raise ValueError('no owned installation marker')
        units=subprocess.check_output(['systemctl','list-units','--all','--no-legend','--plain','mid-edge@*.service'],text=True)
        for line in units.splitlines():subprocess.run(['systemctl','stop',line.split()[0]],check=True)
        uninstall(root,a.purge_state)
    else:uninstall(root,a.purge_state)
    if a.activate:
        subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['udevadm','control','--reload-rules'],check=True)
        if a.action=='install':
            for device in sorted(Path('/sys/class/tty').glob('tty*')):
                metadata=subprocess.run(['udevadm','info','--query=property','--path',str(device)],text=True,capture_output=True,timeout=5)
                if metadata.returncode:continue
                props=dict(x.split('=',1) for x in metadata.stdout.splitlines() if '=' in x)
                if matches(config,props):
                    name=device.name
                    if not re.fullmatch(r'tty(?:USB|ACM)[0-9]+',name):raise ValueError('unsupported tty name')
                    subprocess.run(['udevadm','trigger','--action=add','--sysname-match='+name],check=True)
                    subprocess.run(['systemctl','start','mid-edge@'+name+'.service'],check=True)
    print(json.dumps(dict(action=a.action,root=str(root),activated=a.activate)))

if __name__=='__main__':main()

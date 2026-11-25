from pathlib import Path
import yaml,hashlib,re,json,sys
p=Path('F:/')
bak=max(p.glob('eora-backup-*'),key=lambda a:a.stat().st_mtime_ns)
def read(name,base=p):return (base/name).read_text(encoding='utf-8-sig')
def parse(name,base=p):return yaml.safe_load(read(name,base))
cmd=read('cmdline.txt');old=read('cmdline.txt',bak)
meta=parse('meta-data');user=parse('user-data');olduser=parse('user-data',bak)
inst=meta['instance-id'];payload=read('eora-firstboot.sh')
net=parse('network-config');w=net.get('network',net)['wifis']['wlan0'];auth=next((x['auth'] for x in w['access-points'].values() if isinstance(x,dict) and 'auth' in x),{})
normal=lambda line:re.sub(r'(?<=;)i=[^;\s]+','i=ID',' '.join(line.split()))
checks={'original_cmd_sha':hashlib.sha256((bak/'cmdline.txt').read_bytes()).hexdigest()=='5f9db4b514c9a76094a5e96901e471b960c29352b8adb27356413258c92a92b5','cmdline_single':len(cmd.splitlines())==1,'instance_match':';i='+inst in cmd and inst.startswith('eora-air-04-') and inst not in old,'boot_args_preserved':normal(cmd)==normal(old),'hostname':meta['local-hostname']==user['hostname']=='eora-air-04','imager_user_ssh_preserved':all(user.get(k)==olduser.get(k) for k in ['user','users','ssh_pwauth','ssh_authorized_keys']),'installer_once':user['runcmd'].count(['bash','/boot/firmware/eora-firstboot.sh'])==1,'installer_04':"EORA_HOST='eora-air-04'" in payload,'asynchronous_start':'systemctl start --no-block eora-firstboot.service' in payload,'wifi':auth.get('key-management')=='eap' and bool(auth.get('identity') and auth.get('password'))}
print(json.dumps(checks));sys.exit(0 if all(checks.values()) else 1)

"""Refresh only actual verified A/B runtime metadata, preserving USB bindings."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--results',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-014');out.mkdir(parents=True,exist_ok=False)
path=ROOT/'hardware/eora_hub_400tb/bindings.local.json';before=path.read_bytes();(out/'bindings.before.json').write_bytes(before);data=json.loads(before)
updates=[]
for source in a.results:
 source=source.resolve();assert source.is_relative_to(ROOT/'simulation/outputs/H-014');r=json.loads(source.read_bytes());assert r['success'] and r['closed'];info=r['after_info'];stats=r['stats'];assert stats['radio'] is False and stats['queue_depth']==0
 b=next(b for b in data['bindings']if b['node_id']==info['node_id']);assert b['port']==r['port']
 b.update(verified_build_id=info['build_id'],last_verified_boot_id=info['boot_id'],runtime_uart_baud=info['uart_baud'],last_info_source=str(source),last_info_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),firmware_state='H014 application verified idle after app-only update',note='OLED API2 driver READY; physical pixels remain unverified')
 updates.append(dict(node_id=b['node_id'],port=b['port'],build_id=info['build_id'],boot_id=info['boot_id'],source=str(source)))
blob=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8');temporary=path.with_suffix('.tmp.json');temporary.write_bytes(blob);temporary.replace(path)
(out/'bindings.after.json').write_bytes(blob);(out/'result.json').write_text(json.dumps(dict(updates=updates,before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(blob).hexdigest()),indent=2));print(json.dumps(updates))

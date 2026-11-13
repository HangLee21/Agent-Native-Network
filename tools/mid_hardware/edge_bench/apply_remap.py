"""Apply an actual A/C ROM MAC mapping; never assume USB/COM order is identity."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();source=a.source.resolve();out=a.output.resolve();assert source.is_relative_to(ROOT/'simulation/outputs/H-012') and out.is_relative_to(ROOT/'simulation/outputs/H-012');out.mkdir(parents=True,exist_ok=False)
mapping=json.loads(source.read_bytes())['ports'];labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_bytes())['labels'];assert all(x['success'] and x['closed'] and x['flash_writes']==0 for x in mapping) and {x['rom_mac']for x in mapping}=={labels[k]for k in 'AC'}
path=ROOT/'hardware/eora_hub_400tb/bindings.local.json';before=path.read_bytes();(out/'bindings.before.json').write_bytes(before);data=json.loads(before)
for x in mapping:
 b=next(b for b in data['bindings']if b['node_id']==x['rom_mac']);b.update(port=x['device'],vid=x['vid'],pid=x['pid'],location=x['location'],hwid=x['hwid'],serial_number='',last_verified_boot_id=None,verified_build_id=None,firmware_state='Actual ROM MAC rebound after USB change; application verification pending',last_ROM_identity_source=str(source),last_ROM_identity_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
blob=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode();temp=path.with_suffix('.tmp.json');temp.write_bytes(blob);temp.replace(path);(out/'bindings.after.json').write_bytes(blob);print(json.dumps({x['rom_mac']:x['device']for x in mapping}))

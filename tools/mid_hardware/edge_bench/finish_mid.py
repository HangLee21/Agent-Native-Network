"""Stop owned ABC profiles and clear only mid_deploy/profile for bench use."""
import argparse,datetime,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from tools.mid_edge import Edge
from lease import HardwareLease,reservation
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-012');out.mkdir(parents=True,exist_ok=False);assert reservation()['owner']=='H012'
labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_bytes())['labels'];bindings=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_bytes())['bindings'];results=[]
build='mid-edge-v1-1969b4d894badc0f1c59940fc426b779a14f49b89cca5fedd69a8216d90da143'
with HardwareLease('H012'):
 for label in 'ABC':
  b=next(x for x in bindings if x['node_id']==labels[label]);r=dict(board=label,port=b['port'],started_at=datetime.datetime.now(datetime.timezone.utc).isoformat());edge=None
  try:
   edge=Edge(b['port'],labels[label],460800,log=str(out/f'{label}.events.jsonl'));r['before_info']=edge.info();assert r['before_info']['build_id']==build and r['before_info']['display_api']==2 and r['before_info']['display_enabled']
   r['stop']=edge.command('stop');r['before_clear_stats']=edge.command('stats');assert r['before_clear_stats']['radio'] is False and r['before_clear_stats']['queue_depth']==0
   if r['before_info']['deployment_saved']:r['clear']=edge.command('deployment_clear')
   r['after_info']=edge.info();r['stats']=edge.command('stats');info=r['after_info'];s=r['stats'];assert info['mode']=='idle' and info['radio'] is False and info['deployment_mode']=='mid' and not info['deployment_saved'] and not info['deployment_fault'];assert s['queue_depth']==0 and s['display_hw']==2 and not s['stopping'] and not s['locked_until_reset'];r['success']=True
  except Exception as exc:r.update(success=False,error=repr(exc))
  finally:
   if edge:edge.close()
   r.update(closed=True,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());(out/f'{label}.json').write_text(json.dumps(r,indent=2));results.append(r);print(json.dumps(r),flush=True)
  if not r['success']:break
(out/'result.json').write_text(json.dumps(results,indent=2));raise SystemExit(not(len(results)==3 and all(x['success']for x in results)))

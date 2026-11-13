"""Five-board offline materialization and per-hop evidence. Never opens ports."""
import argparse,importlib.util,json
from pathlib import Path
from unittest.mock import patch
import native
from analyze import strict
sha=native.sha

def path_map(chain,labels):
 if isinstance(chain,str):chain=list(chain.replace('-','').replace(',',''))
 if len(chain)!=5 or set(chain)!=set('ABCDE'):raise ValueError('chain must contain A-E exactly once')
 forward=[labels[x] for x in chain]
 return [forward,list(reversed(forward))]

def materialize(package,assets,case,infos,run_id,labels,chain=None):
 """Inputs are producer-owned package/case paths, fresh info objects and bindings."""
 package=Path(package);assets=Path(assets);labels=labels.get('bindings',labels.get('labels',labels))
 if set('ABCDE')-set(labels) or any(not labels[x] for x in 'ABCDE') or len({labels[x] for x in 'ABCDE'})!=5:raise ValueError('five distinct real labels required')
 manifest_path=package/'PACKAGE_MANIFEST.json';manifest=strict(manifest_path.read_bytes());build=manifest['build_id'];package_hash=sha(manifest_path)
 index_path=assets/'INDEX.json'
 if not index_path.exists():assets=assets/'cases';index_path=assets/'INDEX.json'
 index=strict(index_path.read_bytes());cases=index['cases'];entry=next(x for x in cases if x['case']==case);ordinal=next(i for i,x in enumerate(cases) if x['case']==case)
 folder=assets/case;update_path=folder/'network_update.json';update=strict(update_path.read_bytes())
 if set(update['nodes'])!={labels[x] for x in 'ABCDE'} or len(update['nodes'])!=5 or len(update['flows'])!=2:raise ValueError('exactly five bound nodes and two flows required')
 if (folder/'solution.json').exists() and strict((folder/'solution.json').read_bytes()).get('status')!='optimal':raise ValueError('SOCP not optimal')
 normalized={}
 for label in 'ABCDE':
  mac=labels[label];r=infos.get(mac,infos.get(label))
  if not isinstance(r,dict) or (r.get('schema'),r.get('event'),r.get('cmd'),r.get('ok'),r.get('node_id'),r.get('build_id'),r.get('firmware'),r.get('mode'))!=('mid.serial.v1','command_result','info',True,mac,build,'mid-espnow','idle') or type(r.get('boot_id')) is not int or not 1<=r['boot_id']<=0xffffffff or any(r.get(k)is not False for k in ['radio','stopping','locked_until_reset']):raise ValueError('fresh matching five-board idle info required: '+label)
  normalized[mac]=r
 if chain is None and case.startswith('chain_'):chain=case[6:]
 paths=path_map(chain,labels) if chain else []
 if paths:
  expected={(p[i],p[0],p[-1]):p[i+1] for p in paths for i in range(4)}
  actual={(r['node'],r['src'],r['dst']):r['gateways'] for r in update['routes']}
  if set(actual)!=set(expected) or any(len(actual[k])!=1 or actual[k][0]['node']!=v or actual[k][0]['weight']<=0 for k,v in expected.items()):raise ValueError('SOCP output does not form specified chains; no post-hoc route masking')
  if {(f['src'],f['dst']) for f in update['flows']}!={(p[0],p[-1]) for p in paths}:raise ValueError('controlled flow endpoints mismatch')
 spec=importlib.util.spec_from_file_location('five_package_bridge',package/'source/tools/mid_baseline/bridge/bridge.py');bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
 publisher=labels['A'];boot=normalized[publisher]['boot_id'];seq_start=1001+100*ordinal;actions=[]
 for mac in normalized:actions.append(dict(board=mac,command=dict(cmd='start',nonce='e2-start-'+mac[-2:],publisher=publisher,publisher_boot=boot),require_reply_ok=True))
 for seq in range(seq_start,seq_start+3):actions.append(dict(board=publisher,command=dict(cmd='config',nonce='e2-config-'+str(seq),frame_hex=bridge.pack(update,publisher,boot,seq).hex()),at_config_seconds=seq-seq_start,require_reply_ok=True))
 actions.append(dict(gate='all config_applied and route_selected match required_routes',required_routes=update['routes'],config_seq_minimum=seq_start+2,timeout_seconds=5,abort_on_timeout=True))
 for mac in normalized:actions.append(dict(board=mac,command=dict(cmd='stats',nonce='e2-base-'+mac[-2:]),require_reply_ok=True))
 for f in update['flows']:
  for i in range(5):
   payload=('F'+str(ordinal)+'-'+str(i)).ljust(16,'.').encode().hex()
   actions.append(dict(board=f['src'],command=dict(cmd='send',nonce=f'e2-five-{ordinal}-{f["src"][-2:]}-{i}',dst=f['dst'],payload_hex=payload),interval_ms=500,require_reply_ok=True))
  actions.append(dict(gate='bounded drain',seconds=1.5))
 for mac in normalized:actions.append(dict(board=mac,command=dict(cmd='stop',nonce='e2-stop-'+mac[-2:]),require_reply_ok=True))
 actions.append(dict(gate='all radio=false stopping=false locked_until_reset=false',timeout_seconds=2,abort_on_timeout=True))
 for mac in normalized:actions.append(dict(board=mac,command=dict(cmd='stats',nonce='e2-final-'+mac[-2:]),require_reply_ok=True))
 return dict(schema='mid.native.execution_plan.v1',phase='five-board',case=case,run_id=run_id,package_manifest_sha256=package_hash,build_id=build,package=str(package.resolve()),assets_index=str(index_path.resolve()),assets_index_sha256=sha(index_path),network_update_sha256=sha(update_path),labels={x:labels[x] for x in 'ABCDE'},info_boots={m:r['boot_id'] for m,r in normalized.items()},channel=6,flows=[dict(source=f['src'],destination=f['dst'],count=5) for f in update['flows']],paths=paths,required_relay=None,actions=actions,finally_actions=[dict(board=m,command=dict(cmd='stop',nonce='e2-finally-'+m[-2:])) for m in normalized],max_wall_seconds=60,RF_runs=1,user_packets=10,physical_owner='H-005',limitations=['logical graph constraints are not RF disconnection','MAC success is not endpoint delivery','no retries to replace missing endpoint packets','one minimum pair included in ten pairs; twelve scenarios total, 120 packets'])

def audit(plan_path,log_paths,context_path=None):
 """Reuse endpoint checks, then require every real source/intermediate TX edge."""
 plan=strict(Path(plan_path).read_bytes())
 with patch.multiple(native,PACKAGE_HASH=plan['package_manifest_sha256'],BUILD=plan['build_id'],verify=lambda:None):result=native.audit(plan_path,log_paths,context_path)
 events=[]
 for name in log_paths:
  p=Path(name).resolve()
  for number,line in enumerate(p.read_bytes().splitlines(),1):
   try:r=strict(line)
   except (ValueError,UnicodeError):continue
   if isinstance(r,dict) and r.get('direction')=='device_rx' and isinstance(r.get('event'),dict):events.append((r['event'],dict(path=str(p),line=number)))
 for stream in result['streams']:
  path=next((p for p in plan.get('paths',[]) if p[0]==stream['source'] and p[-1]==stream['destination']),None)
  if not path:continue
  proofs=[]
  for identity in stream['identity_evidence']:
   src,boot,seq,dst=identity['identity'];edge_evidence=[]
   for i,node in enumerate(path[:-1]):
    same=lambda e:e.get('origin')==src and e.get('origin_boot')==boot and e.get('seq')==seq and e.get('dst')==dst and e.get('node_id')==node
    tx=[line for e,line in events if same(e) and e.get('event')=='tx_submit' and e.get('next_hop')==path[i+1]]
    rx=[line for e,line in events if same(e) and e.get('event')=='rx_relay'] if i else []
    edge_evidence.append(dict(node=node,next_hop=path[i+1],tx_submit=tx,rx_relay=rx,complete=bool(tx and (not i or rx))))
   proofs.append(dict(identity=identity['identity'],path=path,edges=edge_evidence,endpoint=identity['endpoint'],complete=bool(identity['endpoint'] and all(e['complete'] for e in edge_evidence))))
  stream['hop_evidence']=proofs;stream['controlled_forwarding_verified']=bool(result['evidence_kind']=='hardware_measured' and not result['issues'] and stream['pdr'] is not None and proofs and all(p['complete'] for p in proofs))
 result['schema']='mid.five.audit.v1';result['analyzer_sha256']=sha(__file__);return result

def main():
 ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
 m=sub.add_parser('materialize');m.add_argument('--package',required=True);m.add_argument('--assets',required=True);m.add_argument('--case',required=True);m.add_argument('--infos',required=True);m.add_argument('--labels',required=True);m.add_argument('--run-id',required=True);m.add_argument('--chain')
 a=sub.add_parser('audit');a.add_argument('--plan',required=True);a.add_argument('--log',action='append',required=True);a.add_argument('--context')
 for p in [m,a]:p.add_argument('--output',required=True)
 x=ap.parse_args();target=Path(x.output).resolve()
 if target.exists() or not any(target.is_relative_to((native.ROOT/'simulation/outputs'/t).resolve()) for t in ['E2-016','H-005']):raise ValueError('new owner output required')
 if x.command=='materialize':
  infos={p.stem.removeprefix('info-'):strict(p.read_bytes()) for p in Path(x.infos).glob('info-*.json')};result=materialize(x.package,x.assets,x.case,infos,x.run_id,strict(Path(x.labels).read_bytes()),x.chain)
 else:result=audit(x.plan,x.log,x.context)
 target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
if __name__=='__main__':main()

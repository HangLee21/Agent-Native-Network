import importlib.util,json,hashlib
from pathlib import Path
def materialize(package,assets,case,infos,run,labels,participants="BCDE"):
 package=Path(package);assets=Path(assets);update=json.loads((assets/case/'network_update.json').read_text());active=[labels[x] for x in participants];publisher=labels['B'];build=json.loads((package/'PACKAGE_MANIFEST.json').read_text())['build_id']
 for m in active:
  i=infos[m];assert i['node_id']==m and i['mode']=='idle' and not any(i[k] for k in ['radio','stopping','locked_until_reset'])
 spec=importlib.util.spec_from_file_location('original_bridge',package/'source/tools/mid_baseline/bridge/bridge.py');bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
 actions=[]
 def cmd(m,c,**kw):actions.append(dict(board=m,command=c,**kw))
 for m in active:cmd(m,dict(cmd='start',nonce='start-'+m[-2:],publisher=publisher,publisher_boot=infos[publisher]['boot_id']))
 for seq in [1001,1002,1003]:cmd(publisher,dict(cmd='config',nonce='cfg-'+str(seq),frame_hex=bridge.pack(update,publisher,infos[publisher]['boot_id'],seq).hex()),at_config_seconds=seq-1001)
 routes=[x for x in update['routes'] if x['node'] in active]
 for f in update['flows']:
  row=next(x for x in routes if x['node']==f['src'] and x['src']==f['src'] and x['dst']==f['dst']);assert len(row['gateways'])==1 and row['gateways'][0]['node']==f['dst']
 actions.append(dict(gate='all config_applied and required_routes',required_routes=routes,timeout_seconds=5))
 for m in active:cmd(m,dict(cmd='stats',nonce='base-'+m[-2:]))
 for f in update['flows']:cmd(f['src'],dict(cmd='send',nonce='placeholder',dst=f['dst'],payload_hex='00'))
 for m in active:cmd(m,dict(cmd='stop',nonce='stop-'+m[-2:]))
 actions.append(dict(gate='all radio=false stopping=false locked_until_reset=false',timeout_seconds=2))
 for m in active:cmd(m,dict(cmd='stats',nonce='final-'+m[-2:]))
 return dict(schema='mid.native.execution_plan.v1',run_id=run,case=case,build_id=build,package_manifest_sha256=hashlib.sha256((package/'PACKAGE_MANIFEST.json').read_bytes()).hexdigest(),info_boots={m:infos[m]['boot_id'] for m in active},builds={m:infos[m]['build_id'] for m in active},flows=[dict(source=f['src'],destination=f['dst'],count=20) for f in update['flows']],actions=actions,max_wall_seconds=35,physical_participants=active,configuration_nodes=update['nodes'],absent_node=labels['A'],publisher=publisher,network_update_source=str(assets/case/'network_update.json'),limitations=['A unavailable; original five-slot route table used only for existing direct source->destination forwarding; no A participation claimed.','No saturated-capacity interpretation.'])

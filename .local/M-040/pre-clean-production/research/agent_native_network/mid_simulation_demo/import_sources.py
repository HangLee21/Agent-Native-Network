"""Read actual E1 simulation events for display, preserving source lines.

No solver/engine imports; endpoint receipt is only destination_rx, never a path.
"""
import json
from collections import defaultdict

ANNOTATIONS={'config_install':'节点安装表','observed_state':'延迟状态观察','detection':'检测到状态变化','solve_start':'开始求解','solve_end':'求解完成','config_publish':'发布新表','keep_previous_table':'保持上一有效表'}

def append_engine_indexes(root,indexes,data,source_record):
    engine_versions=set()
    for name in indexes:
        index=root/name;listing=json.loads(index.read_text(encoding='utf-8'))
        if listing.get('status')!='complete':raise ValueError('Only explicitly completed engine indexes are consumed: '+name)
        engine_versions.add(listing.get('engine_sha256'))
        if len(engine_versions)>1:raise ValueError('Engine versions differ; do not silently merge different simulation mechanisms')
        data['sources'].append(source_record(index,'E1实际仿真批次索引'))
        manifest=index.parent/'RUN_MANIFEST.json'
        if manifest.exists():data['sources'].append(source_record(manifest,'E1仿真来源manifest'))
        for entry in listing['runs']:
            directory=root/entry['path'] if entry.get('path') else index.parent/entry['run_id']
            context_path=directory/'context.json';events_path=directory/'events.jsonl';summary_path=directory/'summary.json'
            context=json.loads(context_path.read_text(encoding='utf-8'))
            assert context['evidence_kind']=='software_simulation'
            if any(r['id']==context['run_id'] for r in data['runs']):raise ValueError('Duplicate actual simulator run')
            for path,role in [(context_path,'E1实际仿真条件'),(events_path,'E1实际模拟逐包/控制事件'),(summary_path,'E1引擎汇总（未代替E2分析）')]:data['sources'].append(source_record(path,role))
            raw=[]
            for line,text in enumerate(events_path.read_text(encoding='utf-8').splitlines(),1):
                event=json.loads(text);event['_display_source']={'path':events_path.relative_to(root).as_posix(),'line':line};raw.append(event)
            packets={};installs=[];annotations=[];choices=[]
            for e in raw:
                kind=e['event'];t=e['t_s'];source=e['_display_source'];pid=e.get('packet_id')
                if kind=='generate':
                    packets[pid]={'id':pid,'direction':0 if e['src']=='A' else 1,'src':e['src'],'dst':e['dst'],'generated_s':t,'received_s':None,'accepted':False,'status':'未交付','events':[],'source':source,'seq':e.get('seq'),'payload_tag':e.get('payload_tag')}
                if kind=='config_install':installs.append({'node':e['node'],'t_s':t,'version':e['version'],'initial':e['initial'],'source':source})
                if kind=='route_selected':choices.append({'node':e['node'],'t_s':t,'direction':e['flow'],'next_hop':e['next_hop'],'version':e['version'],'epoch':e['epoch'],'source':source})
                if kind in ANNOTATIONS:
                    detail=[]
                    if 'observed_at_s' in e:detail.append('观察样本='+str(e['observed_at_s'])+'s')
                    if 'version' in e:detail.append('表版本='+str(e['version']))
                    if kind=='config_publish':detail.append('update='+str(e['update_id']))
                    if kind=='solve_end':
                        detail.extend(['status='+e['status'],'模拟计算延迟='+str(e['simulated_compute_delay_s'])+'s','缓存命中='+str(e['cache_hit']),'本次主机查找/计算壁钟='+str(round(e['lookup_or_compute_wall_s'],6))+'s','原计算壁钟='+str(round(e['original_compute_wall_s'],6))+'s'])
                    if e.get('reason'):detail.append(e['reason'])
                    annotations.append({'t_s':t,'kind':ANNOTATIONS[kind],'original_kind':kind,'node':e.get('node'),'detail':'；'.join(detail),'source':source})
                if not pid or pid not in packets:continue
                p=packets[pid]
                if kind=='source_admitted':p['accepted']=True
                if kind=='destination_rx' and e.get('node')==p['dst'] and p['received_s'] is None:p['received_s']=t;p['status']='目的唯一模拟接收'
                if kind in ['drop','queue_drop'] and p['received_s'] is None:p['status']=e.get('reason',kind)
                normalized={'t_s':t,'kind':kind,'node':e.get('node'),'route_version':e.get('route_version'),'source':source}
                if kind=='link_result' and e.get('kind')=='data':normalized.update(kind='link_service_success' if e['success'] else 'hop_failure',src=e['node'],dst=e['next_hop'],p_success=e.get('p_success'),random_key=e.get('random_key'))
                elif 'next_hop' in e:normalized.update(src=e['node'],dst=e['next_hop'])
                elif kind=='rx':normalized.update(kind='hop_success',src=e['previous_hop'],dst=e['node'])
                for key in ['reason','draw','p_success_at_start','capacity_payload_bps','random_key']:
                    if key in e:normalized[key]=e[key]
                p['events'].append(normalized)
            assert len(packets)==240
            data['runs'].append({'id':context['run_id'],'scenario_id':context['scenario_id'],'seed':context['seed'],'arm':'replan' if context['arm']=='adaptive' else 'fixed','original_arm':context['arm'],'packets':list(packets.values()),'installs':installs,'choices':choices,'annotations':annotations,'context':context,'engine_summary':entry,'metrics':None,'timing_note':'理想集中延迟状态传感（传感器传输/丢失未模拟）；观察周期1s、观察延迟0.5s、模拟计算延迟0.2s；500ms下一跳保持。主机求解/缓存查找壁钟另列于事件，有限控制逐板安装。无共享无线竞争、半双工或头部开销；见原始条件与假设。'})

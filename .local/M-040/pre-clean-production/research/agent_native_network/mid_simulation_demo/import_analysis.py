"""Attach explicit E2 analysis to existing E1 replay events; never re-analyze."""
from pathlib import Path
import json

def resolve(root,parent,name):
    path=Path(name)
    if path.is_absolute():return path
    local=parent/path
    return local if local.exists() else root/path

def append_datasets(root,names,data,source_record):
    analyses=[];pair_documents=[]
    for name in names:
        index=root/name;doc=json.loads(index.read_text(encoding='utf-8'))
        data['sources'].append(source_record(index,'E2正式统计索引'))
        if doc.get('schema')=='mid.link.analysis.v1':analyses.append((index,doc));continue
        rows=doc.get('runs',doc.get('analyses',[]))
        for row in rows:
            if isinstance(row,dict) and row.get('schema')=='mid.link.analysis.v1':analyses.append((index,row));continue
            path_name=row if isinstance(row,str) else row.get('path') or row.get('analysis_path')
            if not path_name:raise ValueError('E2 run reference needs actual-schema adapter: '+str(row))
            path=resolve(root,index.parent,path_name)
            analyses.append((path,json.loads(path.read_text(encoding='utf-8'))))
        pair_ref=doc.get('pairs')
        if isinstance(pair_ref,str):
            path=resolve(root,index.parent,pair_ref);pair_documents.append(json.loads(path.read_text(encoding='utf-8')));data['sources'].append(source_record(path,'E2正式配对分析'))
        elif isinstance(pair_ref,dict):pair_documents.append(pair_ref)
        elif isinstance(pair_ref,list):pair_documents.append({'pairs':pair_ref})
    for path,analysis in analyses:
        assert analysis['evidence_kind']=='software_simulation' and analysis['schema']=='mid.link.analysis.v1'
        run=next((r for r in data['runs'] if r['id']==analysis['run_id']),None)
        if run is None:raise ValueError('E2 run has no explicitly selected E1 raw events: '+analysis['run_id'])
        if run['metrics'] is not None:raise ValueError('Duplicate E2 run analysis; choose one explicit dataset version')
        data['sources'].append(source_record(path,'E2逐场正式统计'))
        directions=[{**d,'generated':d['generated_observed'],'delivered':d['delivered_in_window']} for d in analysis['directions']]
        control=analysis['control'];delivered=sum(d['delivered'] for d in directions)
        run['metrics']={'directions':directions,'seconds':analysis['seconds'],'control_updates':control['publications'],'control_bytes':control['tx_bytes'],'control_bytes_layer':control['bytes_layer'],'summary_text':str(delivered)+'/240（60秒内）','metrics_valid':analysis['metrics_valid'],'issues':analysis['issues'],'analysis_source':path.relative_to(root).as_posix(),'shared_inputs':analysis['shared_inputs']}
        for p in run['packets']:
            metric=next((q for q in analysis['packets'] if str(q.get('packet_id'))==p['id'] and q['src']==p['src'] and q['dst']==p['dst']),None)
            if metric:
                p['analysis']={k:v for k,v in metric.items() if k not in ['attempts','forwarding_events','source_refs']}
        if not analysis['metrics_valid']:run['analysis_warning']='E2分析包含不完整/未知覆盖，图中null不填0'
    for doc in pair_documents:
        for pair in doc.get('pairs',[]):
            if any(p['scenario_id']==pair['scenario_id'] and p['seed']==pair['seed'] for p in data['pairs']):raise ValueError('Duplicate paired analysis')
            data['pairs'].append(pair)

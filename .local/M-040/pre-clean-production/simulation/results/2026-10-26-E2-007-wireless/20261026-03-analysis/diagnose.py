"""Bounded read-only comparison of three preselected task pairs; no new policy calls."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
RUN=HERE.parent/'20261026-02-task'
def read(p):return json.loads(p.read_bytes())
def load(n,t,condition):
    directory=RUN/f'seed-005-n{n:03}-t{t:03}-{condition}'
    names=('decisions','events','messages','service_ledger','information_ledger')
    result={name:read(directory/(name+'.json')) for name in names}
    result['source']=str(directory)
    result['hashes']={name:hashlib.sha256((directory/(name+'.json')).read_bytes()).hexdigest() for name in names}
    return result

def capture(run,index,objects,minimum_versions):
    d=run['decisions'][index];actor=d['actor'];at=d['time']
    decision={k:v for k,v in d.items() if k!='observation'}
    decision['global_index']=index;decision['mask']=d['observation'][2][0]
    decision['decision_id']=f'd{index:07}'
    consulted=next(x for x in run['information_ledger'] if x['kind']=='information_consulted'
                   and x['decision_id']==decision['decision_id'])
    facts={x['id']:x for x in run['information_ledger']}
    references=[x for x in consulted['references'] if x['object']=='self_state' and x['object_id'] in objects]
    evidence=[]
    for message in run['messages']:
        body=json.loads(message['payload_utf8'])
        if (message['enqueued_at']>at or body['kind']!='self_state' or body['source'] not in objects
            or body['state']['seq']<minimum_versions[body['source']]):continue
        mid=message['message_id']
        service=[e for e in run['service_ledger'] if e.get('message_id')==mid and e['time']<=at
                 and e['event'] in ('tx_started','tx_completed','replaced','rejected','delivered')
                 and (e['event']!='delivered' or e['recipient']==actor)]
        evidence.append(dict(message_id=mid,source=body['source'],body=body,
            publication_reason=message['publication_reason'],enqueued_at=message['enqueued_at'],
            refresh_origin_message_id=message['refresh_origin_message_id'],service_events=service))
    decision_event=[e for e in run['events'] if e['kind']=='decision'][index]
    actor_events=[e for e in run['events'] if e.get('actor')==actor and e['id']<decision_event['id']
                  and e['kind'] in ('own_state','departure','arrival')]
    return dict(decision=decision,decision_event_id=decision_event['id'],consultation_id=consulted['id'],cache_references=references,
        cache_acquisition_records=[facts[r['fact_id']] for r in references if r['fact_id'] is not None],
        state_messages=evidence,recent_actor_physical_events=actor_events[-4:])

def compare(n,t,left,right):
    a=load(n,t,left);b=load(n,t,right);divergences=[]
    for actor in range(n):
        aa=[(i,d) for i,d in enumerate(a['decisions']) if d['actor']==actor]
        bb=[(i,d) for i,d in enumerate(b['decisions']) if d['actor']==actor]
        for ordinal in range(max(len(aa),len(bb))):
            xx=aa[ordinal] if ordinal<len(aa) else None;yy=bb[ordinal] if ordinal<len(bb) else None
            if xx and yy and (xx[1]['action'],xx[1]['branch'])==(yy[1]['action'],yy[1]['branch']):continue
            def brief(item):
                return None if item is None else dict(index=item[0],time=item[1]['time'],action=item[1]['action'],branch=item[1]['branch'])
            divergences.append(dict(actor=actor,actor_ordinal=ordinal,left=brief(xx),right=brief(yy)));break
    divergences.sort(key=lambda x:min(side['time'] for side in (x['left'],x['right']) if side))
    first=divergences[0];i=first['left']['index'];j=first['right']['index']
    x=a['decisions'][i];y=b['decisions'][j]
    objects=[int(k) for k in x['source_versions'] if x['source_versions'][k]!=y['source_versions'][k]]
    minimum={k:min(x['source_versions'][str(k)],y['source_versions'][str(k)]) for k in objects}
    masks=[dict(action=k,left=u,right=v) for k,(u,v) in enumerate(zip(x['observation'][2][0],y['observation'][2][0])) if u!=v]
    def brief_sequence(ds):return [(d['actor'],d['branch'],d['action']) for d in ds]
    return dict(agents=n,tasks=t,left_condition=left,right_condition=right,per_actor_first_action_divergence=divergences,
        first=first,prior_global_action_sequence_equal=brief_sequence(a['decisions'][:i])==brief_sequence(b['decisions'][:j]),
        first_decision_times_equal=x['time']==y['time'],changed_source_versions=objects,
        task_versions_equal=x['task_versions']==y['task_versions'],mask_differences=masks,
        left=capture(a,i,objects,minimum),right=capture(b,j,objects,minimum),
        sources={left:dict(path=a['source'],hashes=a['hashes']),right:dict(path=b['source'],hashes=b['hashes'])})

def main():
    out=HERE/'mechanism_trace_v2.json'
    if out.exists():raise FileExistsError(out)
    rows=[compare(18,30,'event_fifo','event_latest'),compare(36,60,'event_fifo','event_latest'),
          compare(36,60,'event_latest','refresh_latest')]
    result=dict(scope='Read-only paired trajectory evidence; establishes actual first action/cache/packet association, not a counterfactual attribution of total makespan.',comparisons=rows)
    out.write_bytes((json.dumps(result,indent=2)+'\n').encode())
    for row in rows:
        print(row['agents'],row['left_condition'],row['right_condition'],json.dumps(row['first']),
              'prior_actions_equal',row['prior_global_action_sequence_equal'],'mask',row['mask_differences'])

if __name__=='__main__':main()

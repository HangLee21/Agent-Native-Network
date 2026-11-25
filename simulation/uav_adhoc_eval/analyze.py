import csv,json,math,statistics
from pathlib import Path


def quantile(values,q):
    values=sorted(values)
    if not values:return None
    i=(len(values)-1)*q; lo=int(i); hi=math.ceil(i)
    return values[lo]+(values[hi]-values[lo])*(i-lo)


def analyze(data):
    """Normalized v1: timestamps seconds; deliveries require receiver==dst."""
    packets={}; observed={}; executions={}; samples=[]; links={}; lifetimes=[]; changes=0
    rows=sorted(data['events'],key=lambda e:e['t'])
    for e in rows:
        t=e['t'];kind=e['type']
        if kind in ('offered','admitted','delivered'):
            key=tuple(e[x] for x in ('origin','origin_boot','seq','dst'))
            p=packets.setdefault(key,{})
            if kind=='delivered' and e.get('receiver')!=e['dst']:raise ValueError('delivery requires destination receiver')
            p[kind]=min(p.get(kind,t),t)
            if kind=='offered':
                if type(e.get('reachable_at_offer')) is not bool:raise ValueError('offer requires reachability at offer')
                if 'reachable' in p and p['reachable']!=e['reachable_at_offer']:raise ValueError('conflicting reachability')
                p['reachable']=e['reachable_at_offer']
        elif kind=='neighbor_received':
            key=(e['observer'],e['peer']); generated=e['generated_at']
            if generated>t:raise ValueError('future neighbor generation time')
            old=observed.get(key)
            if old is None or generated>old:observed[key]=generated
        elif kind=='aoi_sample':
            key=(e['observer'],e['peer']); last=observed.get(key)
            samples.append(dict(observer=key[0],peer=key[1],time_s=t,aoi_s=None if last is None else t-last))
        elif kind=='command_executed':
            key=(e['cmd_id'],e['target']);
            if e.get('executor')!=e['target']:raise ValueError('command executor must be target')
            executions.setdefault(key,[]).append(t)
        elif kind=='link':
            key=tuple(sorted((e['a'],e['b'])))
            if e['up'] and key not in links:links[key]=t;changes+=1
            elif not e['up'] and key in links:lifetimes.append(t-links.pop(key));changes+=1
    offered=[p for p in packets.values() if 'offered' in p];admitted=[p for p in offered if 'admitted' in p]
    delivered=[p for p in offered if 'delivered' in p and p['delivered']>=p['offered']]
    reachable=[p for p in offered if p['reachable']];reachable_delivered=[p for p in reachable if p in delivered]
    latency=[p['delivered']-p['offered'] for p in delivered]
    commands={(e['cmd_id'],e['target']):e['t'] for e in rows if e['type']=='command_issued'}
    successes=[(k,ts) for k,ts in executions.items() if k in commands and ts[0]>=commands[k]]
    result=dict(offered=len(offered),admitted=len(admitted),delivered_unique=len(delivered),
        reachable_offered=len(reachable),reachable_delivered=len(reachable_delivered),
        pdr=len(delivered)/len(offered) if offered else None,
        reachable_pdr=len(reachable_delivered)/len(reachable) if reachable else None,
        delivery_p95_s=quantile(latency,.95),aoi_p95_s=quantile([x['aoi_s'] for x in samples if x['aoi_s'] is not None],.95),
        aoi_samples=len(samples),aoi_unknown=sum(x['aoi_s'] is None for x in samples),
        commands_issued=len(commands),commands_executed=len(successes),duplicate_executions=sum(max(0,len(ts)-1) for _,ts in successes),
        command_p95_s=quantile([ts[0]-commands[k] for k,ts in successes],.95),link_transitions=changes,
        completed_link_lifetime_p95_s=quantile(lifetimes,.95),right_censored_links=len(links),
        warnings=['Reachability is evaluated at offer time; input must specify geometry and sampling basis.',
                  'Only completed link lifetimes enter percentile; active links are right-censored.',
                  'AoI percentile covers known per-pair samples only; unknown count is separate.'])
    pairs={}
    for item in samples:
        key=item['observer']+'|'+item['peer'];bucket=pairs.setdefault(key,[])
        if item['aoi_s'] is not None:bucket.append(item['aoi_s'])
    result['per_neighbor_aoi_p95_s']={k:quantile(v,.95) for k,v in pairs.items()}
    result['per_observer_aoi_p95_s']={observer:quantile([item['aoi_s'] for item in samples if item['observer']==observer and item['aoi_s'] is not None],.95) for observer in sorted({item['observer'] for item in samples})}
    nodes={}
    for identity,p in packets.items():
        if 'offered' not in p:continue
        bucket=nodes.setdefault(identity[0],dict(offered=0,delivered=0))
        bucket['offered']+=1
        if 'delivered' in p and p['delivered']>=p['offered']:bucket['delivered']+=1
    result['per_origin']={k:dict(v,pdr=v['delivered']/v['offered']) for k,v in nodes.items()}
    return result,samples


def run(input_path,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    data=json.loads(Path(input_path).read_text(encoding='utf-8'));result,samples=analyze(data)
    (output/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    with (output/'aoi.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['observer','peer','time_s','aoi_s']);w.writeheader();w.writerows(samples)
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();print(json.dumps(run(a.input,a.output)))

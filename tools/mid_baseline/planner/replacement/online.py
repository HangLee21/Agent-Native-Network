"""M-019 offline model conversion / independent runtime SOCP worker, no ports."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='2'
import argparse,json,sys,time,datetime,math,statistics,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner import solve
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'bridge'))
from bridge import pack,mac

def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,obj):Path(p).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def labels_from(p):
    d=load(p);v=d.get('labels',d.get('bindings'));labels={k:v[k] for k in 'ABCDE'}
    if len({mac(x) for x in labels.values()})!=5:raise ValueError('five distinct actual MACs')
    return labels

def model_from_windows(source,labels,output):
    """Sample variance of observed per-window service, never saturation capacity."""
    raw=load(source);rows=raw if isinstance(raw,list) else raw['windows'];samples={};sources={}
    for index,w in enumerate(rows):
        src=labels.get(w['src'],w['src']);dst=labels.get(w['dst'],w['dst'])
        if src==dst or src not in labels.values() or dst not in labels.values():raise ValueError('window node')
        seconds=float(w['window_s']);size=w['payload_bytes'];scheduled=w['scheduled'];accepted=w['accepted'];rx=w['rx_unique']
        if not math.isfinite(seconds) or seconds<=0 or type(size)!=int or size<=0:raise ValueError('window duration/payload')
        # Arrival-time windows can contain packets accepted in the previous window;
        # do not truncate a real burst or enforce per-bin causal count inequalities.
        if any(type(x)!=int or x<0 for x in (scheduled,accepted,rx)):raise ValueError('window counts')
        if w.get('valid') is not True or not w.get('raw_source'):raise ValueError('valid capture/raw_source required; no bad windows silently filtered')
        key=(src,dst);samples.setdefault(key,[]).append(rx*size*8/seconds);sources.setdefault(key,[]).append(dict(row=index,raw_source=w['raw_source'],scheduled=scheduled,accepted=accepted,rx_unique=rx,window_s=seconds))
    edges=[]
    for (src,dst),values in samples.items():
        if len(values)<2:raise ValueError('at least2 nonoverlapping windows/edge to estimate sample variance')
        edges.append(dict(src=src,dst=dst,mean=statistics.mean(values),variance=statistics.variance(values),windows=len(values),observations=sources[src,dst]))
    model=dict(schema='mid.replacement.model.v1',unit='payload_bits_per_second',edges=edges,window_source=str(Path(source).resolve()),window_sha256=digest(source),provenance='Empirical unique-payload service at recorded offered load, sample variance across host-time windows. Lower-bound service observation, NOT estimated saturation capacity or calibrated channel uncertainty. Independent-link SOCP approximation inherited.',headroom_factor=1)
    with Path(output).open('x',encoding='utf-8') as f:json.dump(model,f,indent=2)
    return model

def scenario(labels,graph,output):
    doc=dict(schema='mid.replacement.scenario.v1',labels=labels,graph=graph,endpoints=['A','B'],initial_members=list('ABCD'),exit='C',replacement='E',after_members=list('ABDE'),initial_logical_chain=list('ACDB'),after_logical_chain=list('AEDB'),duration_s=60,trigger_target_s=20,payload_bytes=32,packets_per_direction_per_s=2,total_planned_per_run=240,
        pairs=[dict(pair=i+1,order=['fixed','replan'] if i%2==0 else ['replan','fixed']) for i in range(5)],
        arm_rules=dict(fixed='Keep identical initial table after same external C stop / E start; no solve or config. Keep source scheduler running.',replan='After actual event, invoke worker using actual survivors ABDE/current model; broadcast new table to live members only. Never wait for C.'),
        requirements=['Same pre table/model/demand/traffic/events per pair; reset same initial state between runs','Keep sender scheduler separate from Popen worker. Record planned, command-admitted, tx_submit, endpoint RX independently; no_route does not cancel future sends.','Before exit prove C carried actual data (and D in service); otherwise no replacement interpretation','Controlled logical graph is explicit in both arms, NOT natural RF disconnect or mobility','Record solve start/end, output usable/config epoch/first replacement relay/endpoint receive on host timeline; do not subtract cross-board clocks','Do not precompute post table for physical replan arm; post solve in replay is smoke test only'])
    with Path(output).open('x',encoding='utf-8') as f:json.dump(doc,f,indent=2)
    return doc

def worker(request,out):
    """Runs in subprocess; only its result.json is published atomically on completion."""
    out=Path(out);out.mkdir(parents=True,exist_ok=False);start=time.monotonic();wall=datetime.datetime.now(datetime.timezone.utc).isoformat()
    record=dict(status='running',solve_start_host_monotonic=start,solve_start_utc=wall,request=request,scope='Model solve only, not physical event/adoption/recovery measurement')
    try:
        s=load(request['scenario']);m=load(request['model']);labels=s['labels'];phase=request['phase'];members=request['members']
        if phase not in ('initial','after') or set(members)!=set(s['initial_members'] if phase=='initial' else s['after_members']):raise ValueError('actual member set differs from this scenario; endpoints cannot be removed')
        if request.get('arm')=='fixed' and phase=='after':raise ValueError('fixed arm must retain initial table, no after solve')
        rate=float(request['demand']);qos=float(request['qos'])
        if not math.isfinite(rate) or rate<0 or not .5<qos<1:raise ValueError('demand/qos')
        if m['unit']!='payload_bits_per_second':raise ValueError('model/demand unit must be payload bits/s')
        nodes=[labels[x] for x in members];n=len(nodes);edges={(e['src'],e['dst']):e for e in m['edges']}
        maxmean=max(e['mean'] for e in m['edges']);penalty=max(1,maxmean*10)**2
        chain=s['initial_logical_chain'] if phase=='initial' else s['after_logical_chain'];allowed=set()
        for a,b in zip(chain,chain[1:]):allowed.add((labels[a],labels[b]));allowed.add((labels[b],labels[a]))
        mean=[[0.0]*n for _ in nodes];variance=[[0.0]*n for _ in nodes]
        for i,a in enumerate(nodes):
            for j,b in enumerate(nodes):
                if i==j:continue
                if s['graph']=='controlled' and (a,b) not in allowed:variance[i][j]=penalty;continue
                if (a,b) not in edges:raise ValueError('missing measured model edge '+a+' '+b)
                e=edges[a,b]
                if any(not math.isfinite(e[k]) or e[k]<0 for k in ('mean','variance')):raise ValueError('invalid model coefficient')
                mean[i][j]=e['mean'];variance[i][j]=e['variance']
        p=dict(nodes=nodes,flows=[dict(src=labels[a],dst=labels[b],rate=rate,qos=qos) for a,b in [('A','B'),('B','A')]],mean=mean,variance=variance,channel_provenance=dict(model_path=request['model'],model_sha256=digest(request['model']),unit=m['unit'],provenance=m['provenance'],graph=s['graph'],logical_chain=chain if s['graph']=='controlled' else None,nonedge_variance_penalty=penalty if s['graph']=='controlled' else None))
        save(out/'problem.json',p);answer=solve(p);save(out/'solution.json',answer)
        record.update(status=answer['status'],input_sha256=digest(out/'problem.json'),model_sha256=digest(request['model']))
        if answer['status']=='optimal':
            update=answer['update']
            if s['graph']=='controlled':
                for row in update['routes']:
                    if any((row['node'],g['node']) not in allowed for g in row['gateways']):raise ValueError('SOCP retained forbidden logical edge; reject, no post-edit')
                for path in (chain,chain[::-1]):
                    for a,b in zip(path,path[1:]):
                        row=next(r for r in update['routes'] if (r['src'],r['dst'],r['node'])==(labels[path[0]],labels[path[-1]],labels[a]))
                        if len(row['gateways'])!=1 or row['gateways'][0]['node']!=labels[b]:raise ValueError('solver chain not exact, reject')
            save(out/'network_update.json',update)
            frame=pack(update,labels['A'],request['publisher_boot'],request['seq'])
            command=dict(schema='mid.serial.v1',cmd='config',nonce=request['nonce'],frame_hex=frame.hex());save(out/'command.json',command)
            record.update(command=command,update_sha256=digest(out/'network_update.json'),frame_bytes=len(frame),config_members=members)
    except Exception as e:record.update(status='error',error=repr(e))
    record.update(solve_end_host_monotonic=time.monotonic(),solve_end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());record['elapsed_s']=record['solve_end_host_monotonic']-start
    save(out/'result.tmp.json',record);(out/'result.tmp.json').replace(out/'result.json');return record

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('model');a.add_argument('--labels',required=True);a.add_argument('--windows',required=True);a.add_argument('--output',required=True)
    a=sub.add_parser('scenario');a.add_argument('--labels',required=True);a.add_argument('--graph',choices=['controlled','natural'],required=True);a.add_argument('--output',required=True)
    a=sub.add_parser('solve');a.add_argument('--request',required=True);a.add_argument('--output',required=True)
    a=p.parse_args()
    if a.action=='model':model_from_windows(a.windows,labels_from(a.labels),a.output)
    elif a.action=='scenario':scenario(labels_from(a.labels),a.graph,a.output)
    else:
        result=worker(load(a.request),a.output);print(json.dumps(result));return 0 if result['status']=='optimal' else 2
    return 0

if __name__=='__main__':raise SystemExit(main())

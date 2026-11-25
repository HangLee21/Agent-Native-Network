"""Compare paired runs; endpoint and deadlines checked from raw event stream."""
import argparse,collections,hashlib,json,pathlib
p=argparse.ArgumentParser();p.add_argument('base');p.add_argument('candidate');p.add_argument('--output',required=True);a=p.parse_args();out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=False)
def load(path):
 path=pathlib.Path(path);m=json.loads((path/'manifest.json').read_text());s=json.loads((path/'summary.json').read_text());assert m['status']=='completed' and s['core_event_overflows']==0
 offered={};recv={};tags=collections.Counter();nd=collections.Counter()
 with (path/'events.jsonl').open(encoding='utf8') as f:
  for line in f:
   x=json.loads(line);key=(x.get('origin_id'),x.get('origin_boot_id'),x.get('seq'));kind=x['event']
   if kind=='offered':assert key not in offered;offered[key]=(x['time_us'],x['dst_id'],x['payload_hex'],x['geometric_4hop_at_submit'])
   elif kind=='destination_received':
    assert key in offered and key not in recv and x['dst_id']==offered[key][1] and x['bytes_match'];recv[key]=x['time_us']
   elif kind=='deadline_outcome':
    for tag in x.get('observed_sr_tags',[]):tags[tag]+=1
    nd[x['status_1s']]+=1
  total=max(x[0] for x in offered.values());duration=int(m['command'][m['command'].index('--seconds')+1])*1000000
  mature=[k for k,v in offered.items() if v[0]+1000000<=duration];on=sum(k in recv and recv[k]-offered[k][0]<=1000000 for k in mature)
  assert len(offered)==s['offered'] and len(recv)==s['delivered'] and len(mature)==s['eligible_1s'] and on==s['eligible_within_1s'] and sum(nd.values())==len(offered)
  node_rates={}
  for role in ('origin','destination'):
   rates=[]
   for node in range(30):
    keys=[k for k in mature if (k[0] if role=='origin' else offered[k][1])==node]
    if keys:rates.append(sum(k in recv and recv[k]-offered[k][0]<=1000000 for k in keys)/len(keys))
   node_rates[role]={'worst':min(rates),'best':max(rates),'mean':sum(rates)/len(rates),'jain':sum(rates)**2/(len(rates)*sum(v*v for v in rates)) if any(rates) else 0,'count':len(rates)}
  brief={'node_rates':node_rates,'offered':len(offered),'mature':len(mature),'on_time':on,'rate':on/len(mature),'delivered':len(recv),'control_airtime_us':s['control_airtime_us'],'data_airtime_us':s['data_airtime_us'],'control_sent':s['control_sent'],'collisions':s['collision_attempts'],'link_failures':s['link_failures'],'core_overflows':s['core_sr_overflows'],'event_overflows':s['core_event_overflows'],'peer_evictions':s['peer_evicted'],'outcomes':dict(nd),'observed_tags':dict(tags),'manifest_sha256':hashlib.sha256((path/'manifest.json').read_bytes()).hexdigest()}
  return offered,brief,m['source_sha256']
x,b,bhash=load(a.base);y,c,chash=load(a.candidate);assert x==y, 'offered or geometry differ'
result={'status':'passed','same_offers_and_geometric_4hop':True,'same_source_hashes':bhash==chash,'base':b,'candidate':c,'paired_rate_difference':c['rate']-b['rate'],'limitations':['Single synthetic radio scenario; not RF','Observed tags are not mutually exclusive packet loss causes','Different source hashes, if any, must be audited before causal comparison']}
(out/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))

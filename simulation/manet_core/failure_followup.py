"""Correlate observed data-hop failure to later same-flow delivery; not repair latency."""
import collections,hashlib,json,math,pathlib,sys
p=pathlib.Path(sys.argv[1]);out=p/'failure_followup.json'
if out.exists():raise FileExistsError(out)
m=json.loads((p/'manifest.json').read_text());s=json.loads((p/'summary.json').read_text());assert m['status']=='completed' and not s['core_event_overflows'];end=int(m['command'][m['command'].index('--seconds')+1])*1000000;pending={};delays=[];nfail=0;h=hashlib.sha256()
with (p/'events.jsonl').open('rb') as f:
 for raw in f:
  h.update(raw);x=json.loads(raw);kind=x['event'];flow=(x.get('origin_id'),x.get('origin_boot_id'),x.get('dst_id'));t=x['time_us']
  if kind=='sr_7' and str(x.get('reason'))=='5':nfail+=1;pending.setdefault(flow,t)
  elif kind=='destination_received' and flow in pending:delays.append(t-pending.pop(flow))
def pct(p):return sorted(delays)[math.ceil(len(delays)*p)-1]/1000 if delays else None
x={'status':'passed','observed_data_hop_failure_events':nfail,'flow_episodes_with_later_delivery':len(delays),'open_episodes_right_censored':len(pending),'later_delivery_delay_ms_p50':pct(.5),'later_delivery_delay_ms_p95':pct(.95),'events_sha256':h.hexdigest(),'limitations':['Flow episodes merge repeated failures before the next receipt','Delay includes time until another message is generated; it is not route repair time','No later receipt may indicate no later traffic, disconnection, protocol failure, or end-of-run censoring','Synthetic RF, no board measurement']};out.write_text(json.dumps(x,indent=2));print(json.dumps(x))

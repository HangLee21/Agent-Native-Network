"""H-011 one-time immutable snapshot derivation from an existing complete capture."""
import argparse,datetime,hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def source(p):return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def save(p,obj):
 with p.open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-011');out.mkdir(parents=True,exist_ok=False)
 labels_path=ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json';labels=read(labels_path)['labels'];reverse={v:k for k,v in labels.items()}
 folder=ROOT/'simulation/outputs/H-006/20261107-link-service-windows';summary=read(folder/'result.json');windows=read(folder/'windows-1s.json')['windows'];assert summary['status']=='complete' and len(summary['runs'])==10
 edges=[];plans=[];times=[]
 for run in summary['runs']:
  assert run['valid'] and not run['issues'];p=Path(run['run']);plan=read(p/'plan.json');plans.append((plan['build_id'],plan['package_manifest_sha256'],plan['payload_bytes'],plan['offered_packets_per_second']))
  ledger=ROOT/'.local/mid/H-006/RF_runs/links-final'/(p.name+'.json');start=read(ledger)['started_at'];times.append(start)
  for flow in run['flows']:
   assert flow['valid'] and flow['accepted']==flow['scheduled']==flow['submitted']==100
   rows=[(i,w) for i,w in enumerate(windows) if (w['src'],w['dst'])==(flow['src'],flow['dst'])];assert len(rows)==10 and all(w['valid'] for _,w in rows)
   values=[w['bits_per_s'] for _,w in rows];raw=p/'native.jsonl';assert source(raw)['sha256']==rows[0][1]['raw_sha256']
   edges.append(dict(src=reverse[flow['src']],dst=reverse[flow['dst']],src_mac=flow['src'],dst_mac=flow['dst'],
    measured=dict(scheduled=flow['scheduled'],accepted=flow['accepted'],submitted=flow['submitted'],destination_unique=flow['rx_unique'],success_pct=100*flow['rx_unique']/flow['accepted'],
      observed_payload_service_bps=statistics.mean(values),sample_variance_bps2=statistics.variance(values),window_samples=10,window_s=1,observation_s=10,offered_pps=10,payload_bytes=32,one_way_delay_ms=None),
    capture=dict(run_id=p.name,run_started_at_utc=start,direction_started_at_utc=None,direction_ended_at_utc=None,
      host_monotonic_start_ns=min(w['window_start_host_ns'] for _,w in rows),host_monotonic_end_ns=max(w['window_end_host_ns'] for _,w in rows),
      timestamp_scope='Run start from original UTC ledger. Direction interval uses host monotonic time; no UTC conversion anchor available.'),
    sources=dict(raw=source(raw),summary=source(folder/'result.json'),windows=source(folder/'windows-1s.json'),window_row_indices=[i for i,_ in rows],plan=source(p/'plan.json'),context=source(p/'context.json'),run_start=source(ledger)),
    defaults=dict(connected=flow['rx_unique']>0,success_pct=100*flow['rx_unique']/flow['accepted'],capacity_kbps=statistics.mean(values)/1000,delay_ms=10.0),
    parameter_provenance=dict(success_pct='historical_endpoint_delivery_fraction_at_recorded_load; simulator per-attempt probability is a modeling approximation',capacity_kbps='historical_observed_payload_service_used_as_editable_simulation_budget_not_saturated_capacity',delay_ms='unmeasured_editable_model_value')))
 assert len(set(plans))==1 and len(edges)==20 and len({(e['src'],e['dst']) for e in edges})==20
 snapshot=dict(schema='mid.measured.snapshot.v1',snapshot_id='H006-20261107-20directions-10pps32B',evidence_kind='historical_hardware_measurement',labels=labels,
  generated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),capture_run_start_range_utc=[min(times),max(times)],capture_end_at_utc=None,
  build_id=plans[0][0],package_manifest_sha256=plans[0][1],edges=sorted(edges,key=lambda e:(e['src'],e['dst'])),
  limitations=['Historical static same-condition snapshot, not current adjacency or real-time radio state.','All 20 directions are independent records even when their values coincide.',
   'Delivery fraction and injected-load service do not establish RF capacity, calibrated uncertainty or guaranteed PDR.','No synchronized one-way delay measurement; 10ms is editable model input.',
   'Processing-manifest timestamps are not capture timestamps. Exact directional UTC/end timestamps remain null.'])
 save(out/'snapshot.json',snapshot);target=Path(__file__).with_name('measured_snapshot.json');save(target,snapshot)
 template=read(ROOT/'coordination/templates/RUN_MANIFEST.json');template.update(template_only=False,task_id='H-011',run_id=out.name,started_at=snapshot['generated_at_utc'],finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),command=sys.argv,python_executable=sys.executable,output_directory=str(out),status='snapshot_derived',exit_code=0,data_and_weights_sha256={'summary':source(folder/'result.json')['sha256'],'windows':source(folder/'windows-1s.json')['sha256']},limitations=snapshot['limitations'])
 save(out/'RUN_MANIFEST.json',template);print(json.dumps(dict(snapshot_id=snapshot['snapshot_id'],directions=len(edges),samples=sum(e['measured']['accepted'] for e in edges),capture_start_range=snapshot['capture_run_start_range_utc'])))
if __name__=='__main__':main()

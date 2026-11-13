"""Read-only proposed normalized MID evidence API; no serial/firmware imports."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def strict(data):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('duplicate JSON key: '+k)
            result[k]=v
        return result
    def constant(x):raise ValueError('non-finite JSON: '+x)
    return json.loads(data,object_pairs_hook=pairs,parse_constant=constant)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def uint(x):return type(x) is int and x>=0


def oled_issue(row,events):
    """Snapshot references an exact local event, never a nearest timestamp."""
    key=(row.get('node_id'),row.get('boot_id'),row.get('based_on_event_seq'))
    evidence=events.get(key)
    if not evidence:return 'display snapshot missing unambiguous local event source'
    state=row.get('display_state');kind=evidence.get('event')
    allowed={'command_accepted':{'CMD_OK'},'tx_queued':{'TX_QUEUED'},
             'control_applied':{'CFG_APPLIED'},'timeout':{'TIMEOUT'},'failed':{'FAILED'}}
    if kind=='link_callback':allowed[kind]={'LINK_OK' if evidence.get('success') is True else 'LINK_FAILED' if evidence.get('success') is False else 'LINK_UNKNOWN'}
    if kind=='endpoint_rx' and evidence.get('unique_receive') is True and evidence.get('node_id')==evidence.get('destination_id'):
        allowed[kind]={'LOCAL_RX'}
    if evidence.get('mode')=='ann' and kind=='ann_confirmed':allowed[kind]={'ANN_CONFIRMED'}
    if state not in allowed.get(kind,set()):return 'display state exceeds referenced event semantics'
    return None


def analyze_files(config_path,log_paths,context_path=None):
    """Return mid.validation.analysis.v1; writes nothing. Contract is proposed."""
    cfg=strict(Path(config_path).read_bytes());run=cfg['run_id']
    if cfg.get('schema')!='mid.validation.config.v1' or cfg.get('evidence_kind') not in {'synthetic','hardware_measured'}:
        raise ValueError('explicit validation config/evidence kind required')
    sources=[];events=[];issues=[]
    for name in log_paths:
        path=Path(name).resolve();raw=path.read_bytes()
        if len(raw)>16*1024**2:raise ValueError('input exceeds 16MiB')
        sources.append(dict(path=str(path),sha256=sha(path)))
        for line_no,line in enumerate(raw.splitlines(),1):
            try:r=strict(line)
            except (ValueError,UnicodeError):issues.append('malformed JSON');continue
            if not isinstance(r,dict):issues.append('non-object row');continue
            capture_kind=None
            if 'direction' in r:
                if r['direction']!='device_rx':continue
                capture_kind=r.get('evidence_kind');r=r.get('event')
            if not isinstance(r,dict) or r.get('schema')!='mid.validation.event.v1':
                issues.append('unrecognized normalized event schema');continue
            if r.get('run_id')!=run:continue
            r=dict(r,_source=dict(path=str(path),line=line_no),_capture_kind=capture_kind)
            events.append(r)
    context=None
    if cfg['evidence_kind']=='hardware_measured':
        if context_path is None:raise ValueError('hardware requires immutable H-005 capture context')
        context=strict(Path(context_path).read_bytes())
        if (context.get('task_id')!='H-005' or context.get('run_id')!=run or context.get('status')!='capture_complete'
            or context.get('evidence_kind')!='hardware_measured'):raise ValueError('wrong hardware capture context')
        if not cfg.get('input_freezes') or context.get('input_freezes')!=cfg['input_freezes']:
            raise ValueError('frozen E1/H source hashes missing or mismatched')
        if any(context.get('log_sha256',{}).get(s['path'])!=s['sha256'] for s in sources):raise ValueError('capture log hash mismatch')
        if any(r['_capture_kind']!='hardware_serial' or r.get('evidence_kind')=='synthetic' for r in events):
            raise ValueError('synthetic/raw provenance cannot establish hardware')
    stream_keys=[(s['flow_id'],s['source_id'],s['destination_id']) for s in cfg['streams']]
    if len(set(stream_keys))!=len(stream_keys):raise ValueError('duplicate stream definition')
    if any(not uint(s.get('expected_generated')) or s['expected_generated']==0 or s['source_id']==s['destination_id'] for s in cfg['streams']):
        raise ValueError('positive generated count and distinct endpoints required')
    event_sources={};ambiguous=set()
    for r in events:
        key=(r.get('node_id'),r.get('boot_id'),r.get('event_seq'))
        if not isinstance(key[0],str) or not isinstance(key[1],str) or not uint(key[2]):
            issues.append('missing logger/boot/event sequence');continue
        if key in event_sources:ambiguous.add(key)
        event_sources[key]=r
    for key in ambiguous:event_sources.pop(key,None)
    if ambiguous:issues.append('duplicate logger event identity')
    display_issues=[]
    for r in events:
        if r.get('event')=='display_snapshot':
            reason=oled_issue(r,event_sources)
            if reason:display_issues.append(dict(reason=reason,source=r['_source']))
    streams=[]
    for s in cfg['streams']:
        generated={};received={};duplicates=0;local_issues=[];counts=Counter();control_bytes=0
        for r in events:
            if r.get('event')=='control_tx_submit' and uint(r.get('frame_bytes')):control_bytes+=r['frame_bytes']
            if (r.get('flow_id'),r.get('origin_id'),r.get('destination_id'))!=(s['flow_id'],s['source_id'],s['destination_id']):continue
            counts[r['event']]+=1
            if not isinstance(r.get('origin_boot_id'),str) or not uint(r.get('seq')):
                local_issues.append('missing transaction identity');continue
            key=(r['origin_id'],r['origin_boot_id'],r['flow_id'],r['destination_id'],r['seq'])
            if r['event']=='generated':
                if r.get('node_id')!=s['source_id'] or r.get('boot_id')!=r['origin_boot_id']:
                    local_issues.append('generation not on source boot');continue
                if key in generated:local_issues.append('duplicate generated identity')
                generated[key]=r
            if r['event']=='endpoint_rx' and r.get('node_id')==s['destination_id']:
                if type(r.get('unique_receive')) is not bool:
                    local_issues.append('unique_receive must be boolean');continue
                if not r['unique_receive']:duplicates+=1;continue
                if not uint(r.get('payload_bytes')):
                    local_issues.append('unknown payload length');continue
                if key in received:duplicates+=1
                else:received[key]=r
        if len(generated)!=s['expected_generated']:local_issues.append('generated count differs from plan')
        if set(received)-set(generated):local_issues.append('unmatched receiver identity')
        if any(generated[k].get('payload_bytes')!=received[k]['payload_bytes'] for k in received if k in generated):
            local_issues.append('source/receiver payload mismatch')
        coverage=s.get('source_log_complete') is True and s.get('receiver_log_complete') is True
        if cfg['evidence_kind']=='hardware_measured':
            coverage=coverage and all(context.get('coverage',{}).get(n) is True for n in [s['source_id'],s['destination_id']])
        known=coverage and not local_issues and not issues and bool(generated)
        reason=None if known else 'coverage_or_log_integrity_or_generation_count_unknown'
        window=s.get('measurement_duration_us');valid_window=uint(window) and window>0 and s.get('duration_clock') in {'receiver_local_window','host_monotonic_controlled_window'}
        streams.append(dict(flow_id=s['flow_id'],source_id=s['source_id'],destination_id=s['destination_id'],
            generated_unique=len(generated),destination_unique_rx_observed=len(received),duplicates_observed=duplicates,
            pdr=len(received)/len(generated) if known else None,
            goodput_bps=sum(r['payload_bytes'] for r in received.values())*8e6/window if known and valid_window else None,
            not_observed_at_endpoint=len(set(generated)-set(received)) if known else None,
            expired_events=counts['timeout'],link_callback_events=counts['link_callback'],
            control_submitted_bytes_run_total=control_bytes,rf_retry_count=None,airtime_us=None,rtt_p95_ms=None,
            metric_status=dict(pdr_reason=reason,goodput_reason=reason if reason else None if valid_window else 'measured_window_unknown',rtt_reason='MID_baseline_has_no_correlated_end_to_end_ack'),
            issues=local_issues,identity_evidence=[dict(identity=list(k),generated=v['_source'],endpoint_rx=received[k]['_source'] if k in received else None) for k,v in generated.items()]))
    return dict(schema='mid.validation.analysis.v1',run_id=run,evidence_kind=cfg['evidence_kind'],streams=streams,
        issues=issues,display_issues=display_issues,source_logs=sources,
        source_config=dict(path=str(Path(config_path).resolve()),sha256=sha(config_path)),
        source_context=dict(path=str(Path(context_path).resolve()),sha256=sha(context_path)) if context_path else None,
        analyzer_sha256=sha(__file__),hardware_performance_verified=False if cfg['evidence_kind']=='synthetic' else None,
        limitations=['normalized event contract proposed; E1/H adapter not yet frozen','no RF retries/airtime inferred from SDK submissions','missing endpoint observation is not a source-side timeout','no baseline ACK added for RTT or OLED','control bytes are application submissions, not PHY airtime'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--log',action='append',required=True);p.add_argument('--context');p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output).resolve();root=Path(__file__).resolve().parents[3]/'simulation/outputs/E2-016'
    if out.exists() or not out.is_relative_to(root.resolve()):raise ValueError('new E2-016 output only')
    result=analyze_files(a.config,a.log,a.context)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    return int(bool(result['issues'] or result['display_issues'] or any(s['issues'] for s in result['streams'])))


if __name__=='__main__':raise SystemExit(main())

"""Create stop-only recovery evidence. Does not clear the service or send business."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAC_A = '90:da:72:48:a4:f8'

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def evidence(path):
    p = Path(path).resolve()
    assert p.is_relative_to(ROOT/'simulation/outputs/H-007')
    return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-id',required=True)
    ap.add_argument('--original',type=Path,required=True)
    ap.add_argument('--a-result',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args = ap.parse_args()
    assert len(args.run_id)==24 and all(c in '0123456789abcdef' for c in args.run_id)
    old, current = read(args.original), read(args.a_result)
    assert old['all_ports_closed'] is True
    assert current['success'] is True and current['closed'] is True and current['stop_confirmed'] is True
    info, stats = current['info'], current['stats']
    assert info['node_id']==stats['node_id']==MAC_A and info['device_label']=='A'
    assert info['boot_id']==stats['boot_id'] and info['build_id']==stats['build_id']
    assert info['uart_baud']==stats['uart_baud']==460800
    assert stats['mode']=='idle' and stats['queue_depth']==0
    assert all(stats.get(k) is False for k in ['radio','stopping','locked_until_reset'])
    age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(current['finished_at'])).total_seconds()
    assert 0<=age<=300, 'Need fresh actual A evidence, no historical cached receipt'
    macs=set(read(ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json')['labels'].values())
    stopped=dict(old['stop_confirmed']);stopped[MAC_A]=True
    assert set(stopped)==macs and all(stopped.values())
    receipt=dict(schema='mid.console.cleanup_recovery.v1',run_id=args.run_id,status='verified_stop_only',
                 verified_at=current['finished_at'],stop_confirmed=stopped,all_ports_closed=True,
                 actual_A=dict(mac=MAC_A,boot=info['boot_id'],build=info['build_id'],uart_baud=460800,mode='idle',queue_depth=0),
                 sources=[evidence(args.original),evidence(args.a_result)],
                 original_failure_retained=True,automatic_business_resend=False,
                 scope='Original four stop confirmations plus fresh physical A info/stop/stats; release active only, retain failed result and plan/run identity.')
    target=args.output.resolve();assert target.is_relative_to(ROOT/'.local/mid/H-007/recoveries') or target.is_relative_to(ROOT/'simulation/outputs/H-007')
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
    print(json.dumps(receipt))

if __name__=='__main__':
    main()

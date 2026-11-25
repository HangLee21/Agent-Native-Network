"""Save simulated/no-fix position commands and query commands; no device access."""
from pathlib import Path
import argparse,json,datetime,sys
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
    if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
    out=ROOT/'simulation/outputs/E1-026'/a.run;out.mkdir(parents=True,exist_ok=False);start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    commands=[dict(cmd='position_set',nonce='simulated-1',position_boot=7,position_seq=1,source='simulated',fix=True,age_ms=500,lat=31.2345678,lon=121.2345678,accuracy_m=None),dict(cmd='telemetry',nonce='snapshot-1'),dict(cmd='position_set',nonce='no-fix-2',position_boot=7,position_seq=2,source='unavailable',fix=False,age_ms=0,lat=None,lon=None,accuracy_m=None),dict(cmd='telemetry_config',nonce='disable-1',enabled=False,period_ms=10000)]
    for i,cmd in enumerate(commands,1):(out/(str(i)+'-'+cmd['cmd']+'.json')).write_text(json.dumps(cmd,indent=2)+'\n',encoding='utf-8')
    (out/'commands.jsonl').write_text(''.join(json.dumps(c,separators=(',',':'))+'\n' for c in commands),encoding='utf-8')
    m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-026',run_id=a.run,started_at=start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,worktree=str(ROOT),output_directory=str(out),status='passed',exit_code=0,budget=dict(device_access=0),limitations=['Simulated coordinates/format fixtures only. Commands saved, not sent to a physical board.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8');print(out)
if __name__=='__main__':main()

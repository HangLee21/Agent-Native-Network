"""Generate identical five-board field commands, never credentials or device traffic."""
from pathlib import Path
import argparse,datetime,json,sys
ROOT=Path(__file__).resolve().parents[3]
MACS=['90:da:72:48:a4:f8','90:da:72:48:a5:cc','90:da:72:48:a4:e0','90:da:72:48:a5:20','90:da:72:48:a6:98']
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--channel',type=int,required=True);p.add_argument('--pc-id',type=int,default=1);p.add_argument('--group',type=int,default=31);a=p.parse_args()
 if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run) or not 1<=a.channel<=13 or not 1<=a.pc_id<=0xffffffff or not 1<=a.group<=0xffffffff:raise ValueError('invalid name/channel/id')
 out=ROOT/'simulation/outputs/E1-027'/a.run;out.mkdir(parents=True,exist_ok=False);start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 prepare=[dict(cmd='field_pause',nonce='pause-prep'),dict(cmd='stop',nonce='stop-prep'),dict(cmd='route_clear',nonce='clear-dynamic'),dict(cmd='deployment_clear',nonce='clear-static')]
 configure=[dict(cmd='field_gateway',nonce='pc-service',pc_id=a.pc_id,agent_to_pc=True,report_period_ms=30000),dict(cmd='field_config',nonce='agent-config',min_ms=5000,max_ms=10000,min_len=20,max_len=128,payload_mode='english',dest_mode='roster',roster=MACS,start_on_boot=True,checkpoint_s=60,segment=1),dict(cmd='route_config',nonce='radio-config',group=a.group,channel=a.channel,autostart=True),dict(cmd='field_status',nonce='verify-field')]
 for name,rows in [('prepare',prepare),('configure',configure)]:
  (out/(name+'.jsonl')).write_text(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in rows),encoding='utf-8')
 (out/'NOTES.txt').write_text('Each board uses the same roster, excludes itself at runtime. No paths installed. PREPARE changes old mode: H records current state and applies only when idle/authorized. Wait stop radio=false before clears. Inject private IP credentials between prepare and configure using configure_wifi.py. --channel is actual2.4GHz hotspot channel, not an assumed6. Outputs are fixtures, not execution evidence.\n',encoding='utf-8')
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-027',run_id=a.run,started_at=start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,status='passed',exit_code=0,worktree=str(ROOT),output_directory=str(out),budget=dict(device_access=0),limitations=['Generated non-secret config only, no commands sent to hardware.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8');print(out)
if __name__=='__main__':main()

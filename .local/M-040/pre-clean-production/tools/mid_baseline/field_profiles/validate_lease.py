"""Host-check actual bounded entry lease/session function without Wi-Fi APIs."""
from pathlib import Path
import argparse,datetime,json,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
 if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
 out=ROOT/'simulation/outputs/E1-027'/a.run;out.mkdir(parents=True,exist_ok=False);src=ROOT/'firmware/mid_baseline/field_agent/field_ip.c';s=src.read_text(encoding='utf-8');body=s[s.index('int field_ip_lease('):s.index('void field_ip_status(')]
 code='#include <stdint.h>\n#include <assert.h>\n#include <stdio.h>\nstatic struct {uint32_t pc_id;}cfg={9};static int online=1;static uint32_t session,retired_sessions[4];static unsigned retired_session_cursor;static uint64_t lease_until;\n'+body+r'''
int main(void){assert(!field_ip_lease(9,77,100,10000,100,0)&&session==77&&lease_until==10000);assert(!field_ip_lease(9,88,100,10000,100,100)&&session==88&&lease_until==10100);assert(field_ip_lease(9,77,100,10000,100,200)<0&&session==88&&lease_until==10100);assert(field_ip_lease(9,99,99,10000,100,300)<0);assert(field_ip_lease(9,99,100,10001,100,300)<0);online=0;assert(field_ip_lease(9,99,100,10000,100,300)<0);puts("PASS actual lease function: fresh matching boot/PC, bounded expiry, independent current session, retired session rejection, IP loss; no hardware");return 0;}
'''
 (out/'lease_test.c').write_text(code,encoding='utf-8');cmd=['gcc','-std=c99','-Wall','-Wextra','-Werror','-pedantic',str(out/'lease_test.c'),'-o',str(out/'test.exe')];m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-027',run_id=a.run,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=cmd,status='running',worktree=str(ROOT),output_directory=str(out),budget=dict(device_access=0,per_command_s=120),ip_source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),limitations=['Actual lease function with fake IP flag, not real association/UDP/RF.'])
 def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
 save()
 try:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/'compile.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();r=subprocess.run([str(out/'test.exe')],capture_output=True,text=True,timeout=120);(out/'host.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();print(r.stdout);m.update(status='passed',exit_code=0)
 except Exception as e:m.update(status='failed',exit_code=1,error=repr(e))
 m['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();print(json.dumps(dict(status=m['status'],output=str(out))));return m['exit_code']
if __name__=='__main__':raise SystemExit(main())

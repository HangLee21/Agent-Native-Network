"""Bounded host checks for field generator, service routing, bridge and copied OLED renderer."""
from pathlib import Path
import argparse,datetime,json,subprocess,hashlib,shutil,sys
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
 if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
 out=ROOT/'simulation/outputs/E1-027'/a.run;out.mkdir(parents=True,exist_ok=False);base=ROOT/'firmware/mid_baseline/field_agent';m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-027',run_id=a.run,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='running',worktree=str(ROOT),output_directory=str(out),python_executable=sys.executable,budget=dict(per_command_s=120,device_access=0),limitations=['Synthetic same-core/renderer host tests; no real Wi-Fi/IP/RF/powerbank/physical OLED evidence.']);commands=[]
 def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
 save();shutil.copytree(base,out/'source/field_agent');shutil.copy2(ROOT/'firmware/mid_baseline/mid.c',out/'source/mid.c');shutil.copy2(ROOT/'firmware/mid_baseline/mid.h',out/'source/mid.h');base=out/'source/field_agent'
 try:
  for name,files in [('field',['field.c','bridge.c','test_field.c']),('service',['source_route.c','bridge.c','test_service.c']),('plain',['source_route.c','test_source_route.c'])]:
   cmd=['gcc','-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(out/'source'),'-I'+str(base),str(out/'source/mid.c'),*[str(base/f) for f in files],'-o',str(out/(name+'.exe'))];commands.append(cmd);r=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/(name+'-compile.log')).write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();r=subprocess.run([str(out/(name+'.exe'))],capture_output=True,text=True,timeout=120);(out/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();print(name+': '+r.stdout.splitlines()[-1])
  m.update(status='passed',exit_code=0)
 except Exception as e:m.update(status='failed',exit_code=1,error=repr(e))
 m.update(command=commands,source_sha256={str(f.relative_to(out/'source')):hashlib.sha256(f.read_bytes()).hexdigest() for f in (out/'source').rglob('*') if f.is_file()},finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());save();print(json.dumps(dict(status=m['status'],output=str(out))));return m['exit_code']
if __name__=='__main__':raise SystemExit(main())

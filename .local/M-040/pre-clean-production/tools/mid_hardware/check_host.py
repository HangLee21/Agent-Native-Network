"""H-owned finite display checks. Writes only to a new caller-selected run directory."""
import argparse,datetime,hashlib,json,subprocess,sys,time
from pathlib import Path
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[2];out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    module=root/'firmware/mid_display';start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    gcc='C:/Strawberry/c/bin/gcc.exe'
    common=[gcc,'-std=c11','-Wall','-Wextra','-Werror','-I'+str(module/'include'),'-I'+str(module/'src')]
    sources=[str(module/'src/mid_display_model.c'),str(module/'src/mid_display_render.c')]
    jobs=[('compile_model',common+sources+[str(module/'tests/test_model.c'),'-o',str(out/'test_model.exe')]),
          ('compile_fake_backend',common+['-I'+str(module/'tests/fakes')]+sources+[str(module/'src/mid_display_idf.c'),str(module/'tests/test_driver_faults.c'),'-o',str(out/'test_driver_faults.exe')]),
          ('model',[str(out/'test_model.exe')])]+[('fake_fault_'+str(i),[str(out/'test_driver_faults.exe'),str(i)])for i in range(3)]
    records=[]
    for name,command in jobs:
        tick=time.monotonic()
        try:
            p=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=120);code=p.returncode
            stdout=p.stdout;stderr=p.stderr
        except (OSError,subprocess.TimeoutExpired) as exc:code=-998;stdout='';stderr=repr(exc)
        (out/(name+'.stdout.txt')).write_text(stdout,encoding='utf-8');(out/(name+'.stderr.txt')).write_text(stderr,encoding='utf-8')
        records.append({'name':name,'command':command,'exit_code':code,'elapsed_s':time.monotonic()-tick})
        if code:break
    passed=len(records)==len(jobs) and all(r['exit_code']==0 for r in records)
    status='passed' if passed else 'failed'
    (out/'result.json').write_text(json.dumps({'status':status,'checks':records,'hardware_measurements':None,'physical_operations':0},indent=2),encoding='utf-8')
    m=json.loads((root/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
    m.update(template_only=False,task_id='H-005',run_id=out.name,started_at=start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(root),output_directory=str(out),command=sys.argv,python_executable=sys.executable,status=status,exit_code=0 if passed else 1,git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),budget={'per_command_seconds':120,'cpu_jobs':1},dirty_files_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in module.rglob('*') if p.is_file()},limitations=['Synthetic host state/renderer/fake-I2C tests only.','No target link, physical display or RF measurement.','All generated frames and binaries remain inside this new output directory.'])
    (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    print(json.dumps({'status':status,'checks':[{k:r[k]for k in ['name','exit_code','elapsed_s']}for r in records]},indent=2))
    return not passed
if __name__=='__main__':raise SystemExit(main())

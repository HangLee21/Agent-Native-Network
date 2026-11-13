"""Compile display translation units for ESP32-S3 using the preserved IDF toolchain.
This is object compilation, not a linked MID application or physical execution.
"""
import argparse,ctypes,datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parents[2];out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    e1=root/'.local/espnow/E1-015';module=root/'firmware/mid_display'
    compile_db=root/'.local/espnow/H-004/oled-01/build/compile_commands.json'
    row=next(r for r in json.loads(compile_db.read_text()) if r['file'].replace('\\','/').endswith('/ann_oled.c'))
    count=ctypes.c_int();shell=ctypes.windll.shell32
    shell.CommandLineToArgvW.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype=ctypes.POINTER(ctypes.c_wchar_p)
    pointer=shell.CommandLineToArgvW(row['command'],ctypes.byref(count))
    if not pointer:raise RuntimeError('Cannot parse original Windows compiler command')
    original=[pointer[i] for i in range(count.value)]
    ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p];ctypes.windll.kernel32.LocalFree(pointer)
    def physical(value):return value.replace('R:\\',str(e1)+'\\').replace('R:/',e1.as_posix()+'/')
    original=[physical(arg) for arg in original if not arg.startswith('-DANN_BUILD_ID=')]
    env=os.environ.copy();settings=json.loads((e1/'environment.json').read_text())
    env['PATH']=physical(settings['PATH']);env['PYTHONDONTWRITEBYTECODE']='1'
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();records=[];status='passed'
    for name in ['mid_display_model.c','mid_display_render.c','mid_display_idf.c']:
        cmd=list(original);cmd[cmd.index('-c')+1]=str(module/'src'/name);cmd[cmd.index('-o')+1]=str(out/(name+'.obj'))
        cmd+=['-I'+str(module/'include'),'-I'+str(module/'src')]
        start=time.monotonic()
        try:
            p=subprocess.run(cmd,cwd=row['directory'],env=env,capture_output=True,text=True,timeout=120)
            (out/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8');code=p.returncode
        except subprocess.TimeoutExpired:
            (out/(name+'.log')).write_text('Compilation exceeded 120 seconds; stopped, no retry.\n',encoding='utf-8');code=-999
        except OSError as exc:
            (out/(name+'.log')).write_text(repr(exc)+'\nCompiler process did not start; branch stopped.\n',encoding='utf-8');code=-998
        records.append({'source':name,'command':cmd,'exit_code':code,'elapsed_s':time.monotonic()-start})
        if code:status='failed';break
    result={'status':status,'kind':'ESP32-S3 object compilation only','commands':records,'linked_application':False,'device_operations':0}
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    m=json.loads((root/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
    m.update(template_only=False,task_id='H-005',run_id=out.name,started_at=started,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(root),output_directory=str(out),command=sys.argv,python_executable=sys.executable,status=status,exit_code=0 if status=='passed' else 1,git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),budget={'per_command_seconds':120,'build_jobs':1},dirty_files_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(module.rglob('*'))if p.is_file()},data_and_weights_sha256={'source_compile_database':hashlib.sha256(compile_db.read_bytes()).hexdigest()},limitations=['Uses the preserved H-004/E1-015 ESP-IDF v5.5.1 ESP32-S3 configuration.','Only three component translation units compiled; final E1 MID linking/build and device testing pending.','Does not modify the old source, configuration, build outputs or SDK.'])
    (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps({'status':status,'translation_units':len(records),'linked_application':False},indent=2))
    return status!='passed'
if __name__=='__main__':raise SystemExit(main())

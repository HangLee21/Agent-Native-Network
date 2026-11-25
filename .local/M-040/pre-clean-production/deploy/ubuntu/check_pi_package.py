"""Finite synthetic serial/API, wheel install and legacy staging checks. No hardware."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    output=p.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=False)
    files=list((ROOT/'tools/mid_edge').glob('*.py'))+list((ROOT/'deploy/ubuntu').glob('*'))
    files+=[ROOT/'firmware/mid_baseline/field_agent/lora_ref/decoder.py',ROOT/'firmware/mid_baseline/field_agent/lora_ref/CONTRACT.md',ROOT/'firmware/mid_baseline/field_agent/lora_ref/runtime.c']
    hashes={}
    for path in files:
        if not path.is_file():continue
        rel=path.relative_to(ROOT);raw=path.read_bytes();target=output/'source'/rel
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);hashes[rel.as_posix()]=hashlib.sha256(raw).hexdigest()
    manifest=dict(task_id='E2-032',run_id=output.name,started_at=datetime.now(timezone.utc).isoformat(),timezone='Asia/Shanghai',worktree=str(ROOT),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),dirty_files_sha256=hashes,
        command=getattr(sys,'orig_argv',sys.argv),python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,
        data_and_weights_sha256={},config_file=None,seeds=[],budget=dict(max_command_seconds=60),output_directory=str(output),process_id=os.getpid(),
        status='running',finished_at=None,exit_code=None,review_reference=None,limitations=['Synthetic serial and actual loopback HTTP; Windows-host pip target install, no Raspberry Pi/ARM, physical USB, RF or systemd PID1 test.'])
    path=output/'RUN_MANIFEST.json';path.write_text(json.dumps(manifest,indent=2),encoding='utf-8');results=[]
    def run(name,command,*,cwd=ROOT,env=None):
        result=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        (output/(name+'.stdout.txt')).write_text(result.stdout,encoding='utf-8');(output/(name+'.stderr.txt')).write_text(result.stderr,encoding='utf-8')
        results.append(dict(name=name,command=command,exit_code=result.returncode))
        if result.returncode:raise RuntimeError(name+' failed; inspect saved output')
        return result
    try:
        run('unit',[sys.executable,'-X','utf8','-m','unittest','tools.mid_edge.test_lora','tools.mid_edge.hostcheck','tools.mid_edge.test_pending_send','-v'])
        run('build',[sys.executable,'-X','utf8',str(ROOT/'deploy/ubuntu/build_package.py'),'--output',str(output/'package')])
        wheel=next((output/'package').glob('*.whl'));target=output/'installed-site';work=output/'isolated-cwd';work.mkdir()
        run('pip-install',[sys.executable,'-m','pip','--isolated','install','--no-index','--no-deps','--target',str(target),str(wheel)],cwd=work)
        script=r'''
import csv,hashlib,base64,importlib.metadata,json,pathlib,zipfile
import tools.mid_edge,tools.mid_edge.service_api,tools.mid_edge.board_service
from tools.mid_edge.lora import decoder
root=pathlib.Path(tools.mid_edge.__file__).resolve().parents[2]
assert root==pathlib.Path(__import__('os').environ['PYTHONPATH']).resolve()
frame=bytes.fromhex(pathlib.Path(__import__('os').environ['FRAME_HEX']).read_text())
report=decoder().decode_frame(frame)
assert decoder().__file__.endswith('_lora_decoder.py')
assert (root/'tools/mid_sim_console/edge_assets/labels.json').is_file()
assert (root/'research/agent_native_network/mid_sim_console/index.html').is_file()
for item in importlib.metadata.distribution('mid-edge').files:
 if item.hash:
  location=item.locate()
  # pip --target relocates generated console launchers into target/bin while
  # retaining their conventional ../../bin entries in installed RECORD.
  if not location.is_file() and str(item).replace('\\','/').startswith('../../bin/'):
   location=root/'bin'/pathlib.Path(item).name
  raw=location.read_bytes();digest=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
  assert item.hash.value==digest,str(item)
print(json.dumps(dict(imported_from=str(root),decoder=decoder().__file__,version=importlib.metadata.version('mid-edge'),decoded_observer=report['observer_id'],record_hashes='passed')))
'''
        env=dict(os.environ,PYTHONPATH=str(target),FRAME_HEX=str(ROOT/'firmware/mid_baseline/field_agent/lora_ref/samples/frame.hex'))
        run('installed-import-decode',[sys.executable,'-X','utf8','-c',script],cwd=work,env=env)
        run('installed-cli-help',[sys.executable,'-m','tools.mid_edge','--help'],cwd=work,env=env)
        run('installed-service-help',[sys.executable,'-m','tools.mid_edge.board_service','--help'],cwd=work,env=env)
        run('legacy-install-stage',[sys.executable,'-X','utf8',str(ROOT/'deploy/ubuntu/test_install_cli.py'),str(output/'legacy-staging')])
        manifest.update(status='passed',exit_code=0)
    except Exception as exc:
        manifest.update(status='failed',exit_code=1,error=str(exc));raise
    finally:
        manifest.update(finished_at=datetime.now(timezone.utc).isoformat())
        path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        (output/'checks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='passed',commands=len(results),wheel=str(wheel),hardware_tested=False)))


if __name__=='__main__':main()

"""One owned Studio reload for H-020; leave the upstream and board config alone."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

from .runtime import read_json, spawn, startup_lock, StartupError, local_port_free
from .server import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', type=Path, help='Resume this reload after the old owner stopped')
    args = parser.parse_args()
    out = (args.resume or ROOT/'simulation/outputs/H-020'/('reload-'+time.strftime('%Y%m%d-%H%M%S'))).resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-020') or (out/'RESULT.json').exists():
        parser.error('Unfinished H-020 reload output required')
    if not args.resume:
        out.mkdir(parents=True, exist_ok=False)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with startup_lock(ROOT/'.local/mid/H-016/studio-launch.lock'):
        if args.resume:
            saved = json.loads((out/'BEFORE.json').read_text())
            before, pc = saved['studio'], saved['pc']
            if not local_port_free('http://127.0.0.1:8794'):
                raise RuntimeError('Studio port occupied; no replacement started')
        else:
            before = read_json('http://127.0.0.1:8794/api/studio/status')
            pc = read_json('http://127.0.0.1:8791/api/pc/status')
        if before is None or pc is None or before['demo']['running']:
            raise RuntimeError('Existing ready live Studio/upstream required; active demo preserved')
        old = ROOT/'simulation/outputs/H-019/20261110-14b-restore-field-services'
        old_process = json.loads((old/'studio/PROCESS.json').read_text())
        if old_process['pid'] != 3852:
            raise RuntimeError('Unexpected old owner; preserved')
        if not args.resume:
            (out/'BEFORE.json').write_text(json.dumps(dict(studio=before, pc=pc), indent=2), encoding='utf-8')
        (old/'STUDIO_STOP').touch()
        until = time.monotonic()+15
        while not local_port_free('http://127.0.0.1:8794'):
            if time.monotonic() > until:
                raise RuntimeError('Owned Studio did not stop; no replacement started')
            time.sleep(.2)
        command = [sys.executable, '-X', 'utf8', '-m', 'tools.mobile_gateway.studio',
                   '--port', '8794', '--pc-port', '8791', '--demo-port', '8795',
                   '--output', str(out/'studio'), '--stop-file', str(out/'STUDIO_STOP')]
        process = spawn(command, out, 'studio')
        until = time.monotonic()+15
        while True:
            after = read_json('http://127.0.0.1:8794/api/studio/status')
            if after is not None:
                break
            if process.poll() is not None or time.monotonic() > until:
                raise RuntimeError('New Studio failed; inspect stderr')
            time.sleep(.2)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for action, value in [('mode', {'mode':before['mode']}), ('gps', {'enabled':before['fake_gps']})]:
            request = urllib.request.Request('http://127.0.0.1:8794/api/studio/'+action,
                json.dumps(value).encode(), {'Content-Type':'application/json', 'Origin':'http://127.0.0.1:8794'})
            with opener.open(request, timeout=5) as response:
                after = json.load(response)
        pc_after = read_json('http://127.0.0.1:8791/api/pc/status')
        if pc_after['instance_id'] != pc['instance_id']:
            raise RuntimeError('Upstream identity changed unexpectedly')
        result = dict(pid=process.pid, stop_file=str(out/'STUDIO_STOP'), command=command,
                      pc_instance=pc['instance_id'], pc_unchanged=True, studio=after,
                      flash_writes=0, board_commands=0, serial_opens=0,
                      finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        (out/'RESULT.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        manifest = json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
        files = [Path(__file__), ROOT/'tools/mobile_gateway/studio.py', ROOT/'tools/mobile_gateway/lora.py', ROOT/'tools/mobile_gateway/lora_reader.py']
        manifest.update(template_only=False, task_id='H-020', run_id=out.name, started_at=started,
            finished_at=result['finished_at'], worktree=str(ROOT), command=[sys.executable,*sys.argv],
            python_executable=sys.executable, output_directory=str(out), process_id=process.pid,
            dirty_files_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            exit_code=0, status='completed', limitations=['Only Studio reloaded; no LoRa port opened by this reload'])
        (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(json.dumps(dict(output=str(out), pid=process.pid, pc_unchanged=True)))


if __name__ == '__main__':
    main()

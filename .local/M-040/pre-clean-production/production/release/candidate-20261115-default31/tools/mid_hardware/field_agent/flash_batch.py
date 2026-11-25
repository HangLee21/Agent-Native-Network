"""Sequential already-authorized formal app updates using fresh per-port MID identities."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--identities',type=Path,required=True)
    p.add_argument('--handoff',type=Path,required=True)
    p.add_argument('--rollback',type=Path,required=True)
    p.add_argument('--rollback-sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    out=a.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-017'):
        p.error('new H-017 output required')
    out.mkdir(parents=True,exist_ok=False)
    mapping=json.loads(a.identities.read_text(encoding='utf-8'))['ports']
    boards={r['info']['device_label']:r for r in mapping if r.get('success')}
    if set(boards)!=set('ABCDE'):
        p.error('five fresh actual identified boards required for this batch')
    package=json.loads(a.handoff.read_text(encoding='utf-8'))
    image_row=next(r for r in package['binaries'] if r['offset']=='0x10000')
    image=a.handoff.resolve().parent/image_row['file']
    if hashlib.sha256(image.read_bytes()).hexdigest()!=image_row['sha256'] or image.stat().st_size!=image_row['bytes']:
        p.error('formal image hash/size mismatch')
    result=dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),target=package['build_id'],boards=[])
    try:
        for label in 'BCADE':
            board=boards[label]
            info=board['info']
            command=[sys.executable,'-X','utf8','-m','tools.mid_hardware.field_agent.flash','--port',board['usb']['device'],'--mac',info['node_id'],'--current-build',info['build_id'],'--target-build',package['build_id'],'--image',str(image),'--sha256',image_row['sha256'],'--rollback',str(a.rollback.resolve()),'--rollback-sha256',a.rollback_sha256,'--output',str(out/('flash-'+label))]
            print(json.dumps(dict(stage='flashing',label=label,port=board['usb']['device'],app_bytes=image_row['bytes'])),flush=True)
            with (out/('flash-'+label+'.console.log')).open('x',encoding='utf-8') as log:
                run=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
            item=json.loads((out/('flash-'+label)/'RESULT.json').read_text(encoding='utf-8'))
            result['boards'].append(dict(label=label,result=item,command=command,exit_code=run.returncode))
            print(json.dumps(dict(stage='board_result',label=label,success=item['success'],write_calls=item['write_calls'],error=item.get('error'))),flush=True)
            (out/'PROGRESS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            if not item['success'] and item['write_calls']:
                raise RuntimeError('owned write failed; preserve evidence and recover this board before continuing')
    finally:
        result.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),success=len(result['boards'])==5 and all(x['result']['success'] for x in result['boards']))
        (out/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    if not result['success']:
        raise SystemExit(1)


if __name__=='__main__':
    main()

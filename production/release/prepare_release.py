"""Prepare a reviewable candidate from an explicitly selected Git commit and image.

No network, checkout, commit, device access or flashing. Build provenance must be
filled and reviewed separately; archive membership never proves image provenance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--commit',required=True,help='full, explicitly selected commit hash')
    p.add_argument('--image',required=True,type=Path,help='explicitly selected application image')
    p.add_argument('--output',required=True,type=Path,help='new directory under production/release')
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}',args.commit): p.error('完整小写 commit SHA-1 必需')
    out=args.output.resolve(); base=(ROOT/'production/release').resolve()
    if not out.is_relative_to(base) or out==base or out.exists(): p.error('output 必须是 release 下不存在的新目录')
    image=args.image.resolve()
    if not image.is_file() or image.stat().st_size==0: p.error('必须指定非空应用镜像')
    check=subprocess.run(['git','cat-file','-t',args.commit],cwd=ROOT,capture_output=True,text=True)
    if check.returncode or check.stdout.strip()!='commit': p.error('指定提交不存在或不是 commit')
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    info={'source_commit':args.commit,'image_sha256':digest,'image_source':str(image),
          'archive_paths':['firmware','production'],'status':'candidate',
          'warning':'源码提交与镜像的构建关系尚需独立证明；清单必要字段仍为空'}
    if args.dry_run:
        print(json.dumps(info,ensure_ascii=False,indent=2)); return 0
    out.mkdir(parents=True,exist_ok=False)
    try:
        archive=out/'source.tar'
        subprocess.run(['git','archive','--format=tar','--output',str(archive),args.commit,'--','firmware','production'],cwd=ROOT,check=True)
        shutil.copyfile(image,out/'app.bin')
        template=json.loads((base/'manifest.example.json').read_text(encoding='utf-8-sig'))
        template['source_commit']=args.commit
        template['firmware'].update(path='app.bin',sha256=digest)
        (out/'manifest.json').write_text(json.dumps(template,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        info['source_archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
        (out/'SOURCE.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(info,ensure_ascii=False,indent=2)); return 0
    except (OSError,subprocess.CalledProcessError) as exc:
        print(f'打包未完成；保留目录供检查：{exc}',file=sys.stderr); return 1


if __name__=='__main__': sys.exit(main())

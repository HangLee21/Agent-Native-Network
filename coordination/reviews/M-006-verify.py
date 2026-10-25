"""Read-only preservation/archive/link checks; writes this stage's QA record."""
from pathlib import Path
import ast
import gzip
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[2]
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

baseline=read(ROOT/'coordination/reviews/M-006-preservation.json')
changed=[r['path'] for r in baseline['files'] if sha((ROOT/r['path']).read_bytes())!=r['sha256']]
assert not changed, changed
archives=[]
for name in ['2026-10-25-E1-004-causal','2026-10-25-E2-005-service']:
    directory=ROOT/'simulation/results'/name
    manifest=read(directory/'ARCHIVE_MANIFEST.json')
    for r in manifest['files']:
        raw=(ROOT/r['source']).read_bytes()
        stored=(directory/r['archive']).read_bytes()
        decoded=gzip.decompress(stored) if r['compression']=='gzip' else stored
        assert sha(raw)==r['source_sha256'] and sha(stored)==r['stored_sha256'] and raw==decoded, r
    archives.append(dict(path=directory.relative_to(ROOT).as_posix(),files=len(manifest['files']),
                         raw_stored_decoded_verified=True))
sources=[]
for name in ['heteromrta_causal.py','test_heteromrta_causal.py','message_service.py','test_message_service.py','service_replay.py']:
    path=ROOT/'simulation'/name
    raw=path.read_bytes()
    ast.parse(raw)
    sources.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(raw),syntax_valid=True))
modified=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=ROOT,text=True).splitlines()
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
links, missing=0,[]
for rel in sorted(set(modified+untracked)):
    path=ROOT/rel
    if path.suffix!='.md' or not path.is_file():
        continue
    for match in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text(encoding='utf-8-sig')):
        target=unquote(match.strip('<>').split('#')[0])
        if not target or re.match(r'^[a-z]+://',target) or target.startswith('mailto:'):
            continue
        if (path.parent/target).exists():
            links+=1
        else:
            missing.append(dict(file=rel,target=target))
assert not missing,missing
record=dict(completed_date='2026-10-26',base_commit=baseline['base_commit'],
            previous_files_checked=len(baseline['files']),previous_files_changed=changed,
            archives=archives,sources=sources,local_links_checked=links,missing_links=missing,
            figure_rows=55,task_episodes=58,fixed_replays=6,
            independent_review='coordination/reviews/C-006.md',
            independent_review_sha256=sha((ROOT/'coordination/reviews/C-006.md').read_bytes()),
            independent_evidence_sha256=sha((ROOT/'coordination/reviews/C-006-verification.json').read_bytes()),
            report_sha256=sha((ROOT/'research/agent_native_network/CAUSAL_SERVICE_STAGE.md').read_bytes()),
            figure_source_sha256=sha((ROOT/'simulation/results/2026-10-25-E1-004-causal/figures/source_data.csv').read_bytes()))
(ROOT/'coordination/reviews/M-006-consistency.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(preserved=len(baseline['files']),archive_files=sum(x['files'] for x in archives),
                     local_links=links,missing=missing)))

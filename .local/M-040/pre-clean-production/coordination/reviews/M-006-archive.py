"""Archive the two authorized stage outputs without altering original bytes."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
DESTINATIONS = {
    'E1-004': '2026-10-25-E1-004-causal',
    'E2-005': '2026-10-25-E2-005-service',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(task):
    source = ROOT / 'simulation/outputs' / task
    target = ROOT / 'simulation/results' / DESTINATIONS[task]
    if not source.is_dir() or target.exists():
        raise RuntimeError('Source missing or archive already exists')
    all_files = sorted(p for p in source.rglob('*') if p.is_file())
    excluded = [p for p in all_files if '__pycache__' in p.parts or p.suffix == '.pyc']
    files = [p for p in all_files if p not in excluded]
    if not files:
        raise RuntimeError('No evidence to archive')
    target.mkdir(parents=True)
    records = []
    for path in files:
        raw = path.read_bytes()
        rel = path.relative_to(source)
        compress = len(raw) >= 4096 and path.suffix in {'.json', '.jsonl', '.csv', '.log'}
        stored = gzip.compress(raw, mtime=0) if compress else raw
        dest = target / (str(rel) + '.gz' if compress else rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as handle:
            handle.write(stored)
        reread = dest.read_bytes()
        decoded = gzip.decompress(reread) if compress else reread
        if decoded != raw or path.read_bytes() != raw:
            raise RuntimeError(f'Archive mismatch or source still being written: {path}')
        records.append(dict(source=path.relative_to(ROOT).as_posix(),
                            archive=dest.relative_to(target).as_posix(),
                            source_sha256=sha(raw), stored_sha256=sha(reread),
                            source_bytes=len(raw), stored_bytes=len(stored),
                            compression='gzip' if compress else 'none'))
    manifest = dict(task=task, date='2026-10-25',
                    base_commit='ff2157cf75fc98ef1137fa279e945e9d08d3d0a4',
                    excluded_regenerable_bytecode=[p.relative_to(ROOT).as_posix() for p in excluded],
                    files=records)
    (target / 'ARCHIVE_MANIFEST.json').write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return dict(task=task, files=len(records),
                source_bytes=sum(x['source_bytes'] for x in records),
                stored_bytes=sum(x['stored_bytes'] for x in records))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('task', choices=DESTINATIONS)
    args = parser.parse_args()
    print(json.dumps(archive(args.task)))

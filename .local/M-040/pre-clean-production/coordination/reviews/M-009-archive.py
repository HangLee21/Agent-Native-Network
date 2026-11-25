"""Archive a frozen task's complete outputs with reversible compression."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
DESTINATIONS = {'E1-007': '2026-10-26-E1-007-wireless', 'E2-007': '2026-10-26-E2-007-wireless'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('task', choices=DESTINATIONS)
    args = parser.parse_args()
    source = ROOT / 'simulation/outputs' / args.task
    dest = ROOT / 'simulation/results' / DESTINATIONS[args.task]
    inputs = [p for p in sorted(source.rglob('*')) if p.is_file()]
    assert inputs and all('__pycache__' not in p.parts for p in inputs)
    dest.mkdir(parents=True, exist_ok=False)
    rows = []
    for path in inputs:
        raw = path.read_bytes()
        target = dest / path.relative_to(source)
        compressed = len(raw) > 65536 and path.suffix in ('.json', '.jsonl', '.txt', '.log', '.csv')
        if compressed:
            target = target.with_name(target.name + '.gz')
        target.parent.mkdir(parents=True, exist_ok=True)
        if compressed:
            target.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
        else:
            shutil.copyfile(path, target)
        stored = target.read_bytes()
        assert (gzip.decompress(stored) if compressed else stored) == raw
        rows.append(dict(source=path.relative_to(ROOT).as_posix(), stored=target.relative_to(ROOT).as_posix(),
                         bytes=len(raw), stored_bytes=len(stored), gzip=compressed,
                         raw_sha256=sha(raw), stored_sha256=sha(stored)))
    manifest = dict(stage='M-009', task=args.task, originals_retained=True, files=rows)
    (dest / 'ARCHIVE_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(task=args.task, files=len(rows), raw_bytes=sum(r['bytes'] for r in rows),
                         stored_bytes=sum(r['stored_bytes'] for r in rows))))


if __name__ == '__main__':
    main()

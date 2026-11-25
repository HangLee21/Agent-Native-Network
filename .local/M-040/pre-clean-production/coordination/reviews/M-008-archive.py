"""Preserve frozen stage outputs, compressing large text without changing bytes."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
JOBS = {
    'E1-006': ('2026-10-26-E1-006-execution', (
        '20261026-00-preflight', '20261026-01-legacy',
        '20261026-02-recovery', '20261026-03-scale', '20261026-04-analysis')),
    'E2-006': ('2026-10-26-E2-006-scale', ('20261026-01',)),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    for task, (name, runs) in JOBS.items():
        source = ROOT / 'simulation/outputs' / task
        dest = ROOT / 'simulation/results' / name
        assert all((source / run).is_dir() for run in runs)
        dest.mkdir(parents=True, exist_ok=False)
        rows = []
        for run in runs:
            for src in sorted((source / run).rglob('*')):
                if not src.is_file():
                    continue
                raw = src.read_bytes()
                dst = dest / src.relative_to(source)
                compressed = len(raw) > 65536 and src.suffix in ('.json', '.jsonl', '.txt', '.log', '.csv')
                if compressed:
                    dst = dst.with_name(dst.name + '.gz')
                dst.parent.mkdir(parents=True, exist_ok=True)
                if compressed:
                    dst.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
                else:
                    shutil.copyfile(src, dst)
                stored = dst.read_bytes()
                assert (gzip.decompress(stored) if compressed else stored) == raw
                rows.append(dict(source=src.relative_to(ROOT).as_posix(),
                                 stored=dst.relative_to(ROOT).as_posix(),
                                 bytes=len(raw), stored_bytes=len(stored),
                                 raw_sha256=sha(raw), stored_sha256=sha(stored), gzip=compressed))
        manifest = dict(stage='M-008', task=task, date='2026-10-26',
                        originals_retained=True, runs=list(runs), files=rows)
        (dest / 'ARCHIVE_MANIFEST.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        print(json.dumps(dict(task=task, files=len(rows), bytes=sum(r['bytes'] for r in rows),
                             stored_bytes=sum(r['stored_bytes'] for r in rows))))


if __name__ == '__main__':
    main()

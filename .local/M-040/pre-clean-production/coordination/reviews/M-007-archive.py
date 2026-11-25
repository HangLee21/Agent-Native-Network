"""Archive new offline census outputs without modifying inputs or prior results."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'simulation/outputs/E1-005'
DEST = ROOT / 'simulation/results/2026-10-26-E1-005-demand'
RUNS = ('20261026-01-census', '20261026-02-verification')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inputs = [p for run in RUNS for p in sorted((SOURCE / run).rglob('*')) if p.is_file()]
    if len(inputs) != 12:
        raise ValueError(f'Expected 12 frozen output files, got {len(inputs)}')
    DEST.mkdir(parents=True, exist_ok=False)
    records = []
    for src in inputs:
        dst = DEST / src.relative_to(SOURCE)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        if digest(src) != digest(dst):
            raise AssertionError('Archive differs')
        records.append(dict(source=src.relative_to(ROOT).as_posix(),
                            stored=dst.relative_to(ROOT).as_posix(),
                            bytes=src.stat().st_size, sha256=digest(src)))
    manifest = dict(task='M-007', date='2026-10-26', mode='byte-for-byte copy',
                    originals_retained=True, files=records)
    (DEST / 'ARCHIVE_MANIFEST.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(files=len(records), bytes=sum(r['bytes'] for r in records))))


if __name__ == '__main__':
    main()

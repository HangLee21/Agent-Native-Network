"""Prepare the verified Mendeley V2 field from an existing ZIP or local cache.

No downloads or overwrites. See DATA_AUDIT.md for usage and coordinate caveats.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import zipfile

import numpy as np
import scipy.io

REPO = pathlib.Path(__file__).resolve().parents[2]
AUDIT = REPO / 'simulation/results/20261124-M067-v2-data-audit/data_ready.json'
HEIGHTS = (2, 25, 50, 80)
POINTS = ((0, 0, 0), (10, 20, 99), (249, 249, 599), (125, 125, 299))


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def check_file(path, expected_size, expected_sha):
    if not path.is_file() or path.stat().st_size != expected_size or digest(path) != expected_sha:
        raise ValueError('file does not match audited V2 SHA-256/size: ' + str(path))


def copy_new(source, dest):
    with source.open('rb') as src, dest.open('xb') as dst:
        shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)


def publish_new(source, dest):
    """Publish on the same filesystem without replacing an existing file."""
    if os.name == 'nt':
        os.rename(source, dest)  # Windows rename fails if the destination exists.
    else:
        os.link(source, dest)  # POSIX rename would replace an existing destination.


def check_array(path, expected_sha):
    array = np.load(path, mmap_mode='r', allow_pickle=False)
    if array.shape != (250, 250, 600) or array.dtype != np.float64:
        raise ValueError('invalid derived array shape/dtype: ' + str(path))
    del array
    if digest(path) != expected_sha:
        raise ValueError('derived cache does not match audited V2 SHA-256: ' + str(path))


def zip_member(archive, name):
    matches = [item for item in archive.infolist()
               if pathlib.PurePosixPath(item.filename).name == name and not item.is_dir()]
    if len(matches) != 1:
        raise ValueError('ZIP must contain exactly one ' + name)
    return matches[0]


def prepare(target, source_dir=None, zip_path=None):
    if source_dir is None and zip_path is None:
        raise ValueError('supply --zip or --source-dir')
    metadata = json.loads(AUDIT.read_text(encoding='utf-8'))
    if metadata.get('dataset_doi') != '10.17632/bn6n2639xh.2' or metadata.get('version') != 2:
        raise ValueError('unexpected audited manifest version')
    raw = {item['name']: item for item in metadata['files']}
    derived = {item['height_m']: item for item in metadata['derived']}
    if set(derived) != set(HEIGHTS) or len(raw) != 5:
        raise ValueError('incomplete audited manifest')
    target = pathlib.Path(target).resolve()
    source_dir = pathlib.Path(source_dir).resolve() if source_dir else None
    archive = zipfile.ZipFile(zip_path) if zip_path else None
    target.mkdir(parents=True, exist_ok=True)
    ready_path = target / 'data_ready.json'
    existing_ready = ready_path.exists()
    try:
        # Validate every existing destination before creating any destination files.
        for name, item in raw.items():
            existing = target / name
            if existing.exists():
                check_file(existing, item['size'], item['published_sha256'])
        for item in derived.values():
            existing = target / item['path']
            if existing.exists():
                check_array(existing, item['sha256'])
        if existing_ready:
            if any(not (target / name).is_file() for name in raw) or any(
                    not (target / item['path']).is_file() for item in derived.values()):
                raise ValueError('existing data_ready.json has missing assets; refusing to modify')
            old = json.loads(ready_path.read_text(encoding='utf-8'))
            if old.get('dataset_doi') != metadata['dataset_doi'] or old.get('version') != 2:
                raise ValueError('existing data_ready.json has different provenance; refusing overwrite')
            old_raw = {x['name']: x.get('sha256') for x in old.get('files', [])}
            old_derived = {x['path']: x.get('sha256') for x in old.get('derived', [])}
            if old_raw != {k: v['published_sha256'] for k, v in raw.items()} or old_derived != {v['path']: v['sha256'] for v in derived.values()}:
                raise ValueError('existing data_ready.json does not match audited assets; refusing overwrite')

        with tempfile.TemporaryDirectory(prefix='.v2-stage-', dir=target) as tmp:
            stage = pathlib.Path(tmp)
            pending = []
            raw_paths = {}
            for name, item in raw.items():
                dest = target / name
                cached = source_dir / name if source_dir else None
                if dest.exists():
                    raw_paths[name] = dest
                elif cached and cached.exists():
                    check_file(cached, item['size'], item['published_sha256'])
                    staged = stage / name
                    copy_new(cached, staged)
                    check_file(staged, item['size'], item['published_sha256'])
                    pending.append((staged, dest))
                    raw_paths[name] = staged
                elif archive:
                    staged = stage / name
                    with archive.open(zip_member(archive, name)) as src, staged.open('xb') as dst:
                        shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
                    check_file(staged, item['size'], item['published_sha256'])
                    pending.append((staged, dest))
                    raw_paths[name] = staged
                else:
                    raise FileNotFoundError('missing verified raw file: ' + name)
                print('verified', name, flush=True)

            for height in HEIGHTS:
                item = derived[height]
                dest = target / item['path']
                cached = source_dir / item['path'] if source_dir else None
                if dest.exists():
                    check_array(dest, item['sha256'])
                    print('reused target', item['path'], flush=True)
                    continue
                staged = stage / item['path']
                if cached and cached.exists():
                    check_array(cached, item['sha256'])
                    copy_new(cached, staged)
                else:
                    name = f'Dynamic_SEM_1.25km_h{height}m_2.45GHz_600s.mat'
                    key = f'rem{height}m600s'
                    array = scipy.io.loadmat(raw_paths[name], variable_names=[key])[key]
                    if array.shape != (250, 250, 600) or array.dtype != np.float64:
                        raise ValueError('unexpected MAT shape/dtype: ' + name)
                    result = np.lib.format.open_memmap(staged, mode='w+', dtype=np.float64,
                                                       shape=array.shape, fortran_order=True)
                    result[:] = array
                    result.flush()
                    if not all(result[x, y, t] == array[x, y, t] for x, y, t in POINTS):
                        raise ValueError('MAT to NPY point verification failed: ' + name)
                    del result, array
                check_array(staged, item['sha256'])
                pending.append((staged, dest))
                print('prepared', item['path'], flush=True)

            # All staged assets verified. Staging is on the target filesystem.
            for staged, dest in pending:
                publish_new(staged, dest)
            if not existing_ready:
                staged_ready = stage / 'data_ready.json'
                staged_ready.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n',
                                        encoding='utf-8')
                publish_new(staged_ready, ready_path)
            print('ready:', ready_path, flush=True)
    finally:
        if archive:
            archive.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, type=pathlib.Path)
    parser.add_argument('--zip', type=pathlib.Path, help='existing official V2 ZIP')
    parser.add_argument('--source-dir', type=pathlib.Path, help='existing verified raw MAT/PDF and optional NPY cache')
    args = parser.parse_args()
    try:
        prepare(args.target, args.source_dir, args.zip)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print('V2 preparation failed: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

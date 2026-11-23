"""Review/sync committed baseline frontend to ControlSystem/lh; never deploy or push.

Default is a read-only check. --apply requires a clean target frontend and a
conflict-free three-way plan. Missing source files require manual review, not deletion.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile

ROOTS = ('frontend', 'scripts/network-studio', 'START_NETWORK_STUDIO.cmd', 'START_NETWORK_DEMO.cmd')
RECEIPT = 'frontend/.baseline-sync.json'
ROOT = Path(__file__).resolve().parents[2]


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def digest(data):
    # Git checkouts may use CRLF; do not treat only line endings as divergence.
    if b'\0' not in data:
        try:
            data.decode('utf-8')
            data = data.replace(b'\r\n', b'\n')
        except UnicodeDecodeError:
            pass
    return hashlib.sha256(data).hexdigest()


def allowed(name):
    p = PurePosixPath(name)
    return (not p.is_absolute() and '..' not in p.parts and '\\' not in name
            and ':' not in name and name.casefold() != RECEIPT.casefold()
            and (name.startswith('frontend/') or name.startswith('scripts/network-studio/')
                 or name in ROOTS[2:])
            and not any(x.casefold() in ('node_modules', 'dist', '__pycache__', '.git', '.baseline-sync') for x in p.parts)
            and not p.name.casefold().startswith('.env') and p.suffix.lower() not in ('.key', '.pem', '.pfx'))


def destination(target, name):
    if not allowed(name):
        raise ValueError('Path outside managed frontend scope: ' + name)
    path = target.joinpath(*PurePosixPath(name).parts)
    path.resolve().relative_to(target.resolve())
    for item in (path, *path.parents):
        if item == target:
            break
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Symlink/reparse target is not managed: ' + name)
    return path


def archive_files(root, ref):
    names = git(root, 'ls-tree', '-r', '--name-only', ref, '--', *ROOTS).decode('utf-8').splitlines()
    roots = [r for r in ROOTS if any(n == r or n.startswith(r + '/') for n in names)]
    if not roots:
        return {}
    result = {}
    with tarfile.open(fileobj=io.BytesIO(git(root, 'archive', '--format=tar', ref, '--', *roots))) as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile() or not allowed(member.name):
                if member.name == RECEIPT:
                    continue
                raise ValueError('Unsafe/unexpected committed frontend file: ' + member.name)
            result[member.name] = archive.extractfile(member).read()
    return result


def plan_sync(files, bases, target):
    plan = {'add': [], 'update': [], 'unchanged': [], 'conflicts': []}
    for name, data in sorted(files.items()):
        path = destination(target, name)
        if path.exists() and not path.is_file():
            raise ValueError('Target is not a regular file: ' + name)
        current = digest(path.read_bytes()) if path.exists() else None
        if current == digest(data):
            plan['unchanged'].append(name)
        elif current is None and name not in bases:
            plan['add'].append(name)
        elif current is not None and current == bases.get(name):
            plan['update'].append(name)
        else:
            plan['conflicts'].append({'path': name, 'reason': 'target changed/deleted or an unmanaged target exists'})
    for name in sorted(set(bases) - set(files)):
        destination(target, name)
        plan['conflicts'].append({'path': name, 'reason': 'source removed; manual reviewed cleanup required; never auto-delete'})
    return plan


def atomic_write(target, name, data):
    path = destination(target, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', delete=False) as out:
        temporary = Path(out.name)
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    # Resolve and re-check the exact replacement target before any move.
    destination(target, name)
    if temporary.resolve().parent != path.parent.resolve():
        raise ValueError('Unexpected temporary file parent')
    os.replace(temporary, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target', type=Path, required=True, help='ControlSystem Git working tree on branch lh')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='read-only comparison (default)')
    mode.add_argument('--apply', action='store_true', help='apply only a conflict-free plan; no Git writes/push')
    args = ap.parse_args()
    target = args.target.resolve()
    if target == ROOT or target in ROOT.parents or ROOT in target.parents:
        raise ValueError('Source and target must be separate repository trees')
    if Path(git(target, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != target:
        raise ValueError('--target must be the Git root')
    if git(target, 'branch', '--show-current').decode().strip() != 'lh':
        raise ValueError('Target must be ControlSystem/lh; deploy is frozen')
    if not all((target / name).is_file() for name in ('REQUIREMENTS.md', 'WORKFLOW.md', 'backend/pom.xml')):
        raise ValueError('Target does not match the ControlSystem platform layout')
    if git(ROOT, 'status', '--porcelain', '--', *ROOTS).strip():
        raise ValueError('Commit/review baseline frontend changes first; only committed source is exported')
    commit = git(ROOT, 'rev-parse', 'HEAD').decode().strip()
    files = archive_files(ROOT, commit)
    provenance = json.loads(files['frontend/FRAMEWORK_SOURCE.json'])
    receipt_path = target / RECEIPT
    if receipt_path.is_symlink():
        raise ValueError('Receipt must not be a symlink')
    receipt_path.resolve().relative_to(target)
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text('utf-8'))
        if receipt.get('schema') != 'baseline.frontend.sync.v1' or receipt.get('source_repository') != 'HangLee21/Agent-Native-Network':
            raise ValueError('Unrecognized sync receipt')
        bases = receipt['files']
        if not isinstance(bases, dict) or any(not allowed(n) or not isinstance(h, str) or len(h) != 64 for n, h in bases.items()):
            raise ValueError('Invalid receipt scope/checksums')
    else:
        # Bootstrap from the exact original lh commit, never guess a common ancestor.
        base_commit = provenance['upstream_commit']
        git(target, 'merge-base', '--is-ancestor', base_commit, 'HEAD')
        bases = {n: digest(b) for n, b in archive_files(target, base_commit).items()}
    plan = plan_sync(files, bases, target)
    report = dict(schema='baseline.frontend.sync-plan.v1', source_commit=commit,
                  target=str(target), target_branch='lh', deploy='FROZEN', mode='apply' if args.apply else 'check', **plan)
    if args.apply and not plan['conflicts']:
        if git(target, 'status', '--porcelain', '--', *ROOTS).strip():
            raise ValueError('Target frontend has uncommitted/untracked changes; nothing was overwritten')
        for name in plan['add'] + plan['update']:
            atomic_write(target, name, files[name])
        if plan['add'] or plan['update'] or not receipt_path.exists():
            receipt = dict(schema='baseline.frontend.sync.v1', source_repository='HangLee21/Agent-Native-Network',
                           source_commit=commit, files={n: digest(b) for n, b in sorted(files.items())})
            # Receipt is the only metadata path outside allowed(); check its exact resolved location.
            receipt_path.resolve().relative_to(target)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        report['applied'] = True
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 3 if plan['conflicts'] else (0 if args.apply or not (plan['add'] or plan['update']) else 2)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({'error': str(error), 'recovery': 'If --apply was requested, inspect the target Git diff; no automatic reset or deletion is performed.'}, ensure_ascii=True))
        raise SystemExit(1)

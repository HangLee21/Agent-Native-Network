"""Run one H hardware command with a finite child-process deadline and new logs."""
import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--script', type=Path, required=True)
    ap.add_argument('--logs', type=Path, required=True)
    ap.add_argument('--seconds', type=int, required=True)
    ap.add_argument('args', nargs=argparse.REMAINDER)
    a = ap.parse_args()
    assert 0 < a.seconds <= 180
    script = a.script.resolve()
    assert script.is_relative_to(ROOT)
    out = a.logs.resolve()
    assert out.is_relative_to(ROOT / 'simulation/outputs/H-006')
    out.mkdir(parents=True, exist_ok=False)
    tail = a.args[1:] if a.args[:1] == ['--'] else a.args
    cmd = [sys.executable, str(script), *tail]
    result = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'command': cmd, 'timeout_seconds': a.seconds}
    tick = time.monotonic()
    with (out / 'stdout.txt').open('xb') as stdout, (out / 'stderr.txt').open('xb') as stderr:
        try:
            p = subprocess.run(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=a.seconds)
            result.update(exit_code=p.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            result.update(exit_code=124, timed_out=True)
    result.update(elapsed_s=time.monotonic()-tick,
                  finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/'supervisor.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    print((out/'stdout.txt').read_text(errors='replace')[-1200:])
    if result['exit_code']:
        print((out/'stderr.txt').read_text(errors='replace')[-1200:])
    return result['exit_code']

if __name__ == '__main__':
    raise SystemExit(main())

"""Prepare the real upstream before opening an existing or new studio."""
import argparse
import json
from pathlib import Path
import sys
import subprocess
import webbrowser
from .runtime import Bench, StartupError, ensure_runtime


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,help='explicit bench/LAN profile; credentials remain private')
    parser.add_argument('--runtime-dir',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--entry-wait',type=float,default=5)
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args(argv)
    if not 0<=args.entry_wait<=20: parser.error('entry-wait must be 0..20 seconds')
    try:
        bench=Bench(**json.loads(args.config.read_text(encoding='utf-8'))) if args.config else Bench()
        print('Preparing the bench hotspot and wireless upstream before opening the page...',flush=True)
        result=ensure_runtime(bench,runtime_dir=args.runtime_dir,output=args.output,entry_wait=args.entry_wait)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        if result['waiting_for_boards']: print('Services ready; waiting for powered boards to reconnect. The page shows actual state.',flush=True)
        if not args.no_open: webbrowser.open(result['url'])
    except (StartupError,OSError,ValueError,TypeError,subprocess.TimeoutExpired) as exc:
        print('Startup was not completed: '+str(exc),file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':
    main()

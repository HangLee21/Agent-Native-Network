"""Double-click companion: reuse the hardware service or start the existing E2 server."""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
URL = 'http://127.0.0.1:8766/'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='Read-only check; never launches a browser or service')
    args = ap.parse_args()
    running = None
    try:
        with urllib.request.urlopen(URL+'api/status', timeout=2) as response:
            running = json.load(response)
    except (urllib.error.URLError, TimeoutError):
        pass
    if args.check:
        print(json.dumps(dict(url=URL, running=running is not None,
                              hardware=running is not None and running.get('mode') == 'hardware')))
        return 0 if running and running.get('mode') == 'hardware' else 1
    if running:
        if running.get('mode') != 'hardware':
            raise SystemExit('Port8766 is occupied by a different mode. Existing service left unchanged.')
        webbrowser.open(URL)
        return 0
    return subprocess.call([sys.executable, str(ROOT/'tools/mid_console/server.py'),
                            '--hardware', '--port', '8766', '--open'], cwd=ROOT)

if __name__ == '__main__':
    raise SystemExit(main())

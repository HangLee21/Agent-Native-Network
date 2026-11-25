"""Default baseline UI launcher. Preserve legacy services, open only real Vue Studio."""
import argparse
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import quote
import webbrowser

ROOT = Path(__file__).resolve().parents[2]


def http_json(port, path):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        connection.request('GET', path, headers={'Accept': 'application/json', 'Connection': 'close'})
        response = connection.getresponse()
        data = response.read(2 * 1024 * 1024 + 1)
        if response.status != 200 or len(data) > 2 * 1024 * 1024:
            return None
        return json.loads(data)
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        connection.close()


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


def real_preview(root, port):
    # A ControlSystem preview or a Mock-enabled Vite instance must not be reused.
    source = http_json(port, '/FRAMEWORK_SOURCE.json')
    config = http_json(port, '/network-config.json')
    mock = http_json(port, '/network-mock-config.json')
    fs_path = '/@fs/' + quote((root / 'frontend/FRAMEWORK_SOURCE.json').as_posix(), safe='/:')
    actual_root = http_json(port, fs_path)
    return (isinstance(source, dict) and source.get('schema') == 'baseline.frontend.import.v1'
            and actual_root == source and isinstance(config, dict)
            and config.get('schema') == 'network.config.v2'
            and config.get('gatewayRelayPath') == '/__network_gateway'
            and isinstance(mock, dict) and mock.get('enabled') is False)


def ensure_services(root, output=None):
    ready = []
    for port in (8780, 8794):
        value = http_json(port, '/api/v1/lora/topology')
        ok = isinstance(value, dict) and value.get('schema') == 'lora.topology.v1'
        if not ok and port_open(port):
            raise RuntimeError('Port %d belongs to an unrecognized service; left untouched.' % port)
        ready.append(ok)
    if all(ready):
        print('Existing gateway/Studio services reused; no process was restarted.')
        return 0
    if output is None:
        stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + str(time.time_ns())
        output = root / 'simulation/outputs/M-064' / (stamp + '-default-start') / 'studio'
    # Retain the original backend bootstrap, but never open its old UI or change NIC mode.
    command = [sys.executable, '-X', 'utf8', str(root / 'tools/mid_baseline/gateway_probe/start_frontend.py'),
               '--no-browser', '--skip-lab', '--output', str(output)]
    return subprocess.call(command, cwd=str(root))


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--skip-lab', action='store_true', help='Compatibility flag; NIC changes are always disabled here.')
    parser.add_argument('--output', help='Fresh directory for legacy Studio if it must be started.')
    parser.add_argument('--web-port', type=int, default=None)
    args = parser.parse_args(argv)
    try:
        port = args.web_port if args.web_port is not None else int(os.environ.get('NETWORK_WEB_PORT', '10518'))
        if not 1024 <= port <= 65535:
            raise ValueError('Web port must be 1024..65535')
        occupied = port_open(port)
        if occupied and not real_preview(root, port):
            raise RuntimeError('Port %d is occupied by another checkout, Mock or unknown service; not stopped or reused.' % port)
        result = ensure_services(root, args.output)
        if result:
            return result
        url = 'http://127.0.0.1:%d/studio.html' % port
        print('REAL Vue Studio: ' + url)
        print('Local gateway: http://127.0.0.1:8780, LoRa topology v1. Connect explicitly; use clear layout without GPS.')
        print('Legacy UI remains available through START_STUDIO_LEGACY.cmd. No Mock or NIC changes.')
        if occupied:
            print('Reusing verified baseline real-only preview.')
            if not args.no_browser:
                webbrowser.open(url)
            return 0
        if os.name != 'nt':
            raise RuntimeError('This CMD entry requires Windows; use npm run network:real on other systems.')
        launcher = root / 'START_NETWORK_STUDIO.cmd'
        if not launcher.is_file():
            raise RuntimeError('Missing real frontend launcher: ' + str(launcher))
        stop = threading.Event()
        def open_when_ready():
            deadline = time.monotonic() + 180
            while not stop.wait(0.5) and time.monotonic() < deadline:
                if real_preview(root, port):
                    webbrowser.open(url)
                    return
        if not args.no_browser:
            threading.Thread(target=open_when_ready, daemon=True, name='open-real-vue-studio').start()
        env = os.environ.copy()
        env['NETWORK_WEB_PORT'] = str(port)
        # Fixed command, quoted full path; no operator argument is interpolated into CMD.
        command = '"%s" /d /s /c ""%s""' % (os.environ.get('COMSPEC', 'cmd.exe'), launcher)
        try:
            return subprocess.call(command, cwd=str(root), env=env)
        finally:
            stop.set()
    except (OSError, ValueError, RuntimeError) as error:
        print('Studio startup stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

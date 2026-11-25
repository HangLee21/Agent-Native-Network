"""Isolated live-only Studio contract check: no radio, serial, agents or production DB."""
import argparse
import json
from pathlib import Path
import socket
import threading
import urllib.error
import urllib.request

from .server import Gateway, ROOT
from .studio import Studio, StudioHandler
from .sources import Sources
from .replay import Replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    # Hold an unlistened ephemeral loopback port: never query an existing PC/device service.
    with socket.socket() as unavailable:
        unavailable.bind(('127.0.0.1', 0))
        pc_port = unavailable.getsockname()[1]
        state = Studio(out, pc_port)
        sources = Sources(start=False)
        replay = Replay(out / 'isolated-replay.sqlite3', sources.topology, interval=3600)
        fleet = out / 'empty-fleet.json'
        fleet.write_text(json.dumps({'schema_version': 1, 'nodes': []}), encoding='utf-8')
        server = Gateway(('127.0.0.1', 0), state, ROOT / 'research/agent_native_network/mobile_gateway')
        server.RequestHandlerClass = StudioHandler
        server.sources = sources
        server.remote = sources
        server.serial = None
        server.replay = replay
        server.fleet_path = fleet
        server.registry_path = out / 'absent-registry.json'
        server.recovery_path = out / 'absent-recovery.json'
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'

        def call(path, body=None, origin=True):
            headers = {'Content-Type': 'application/json'}
            if origin:
                headers['Origin'] = base
            request = urllib.request.Request(base + path, None if body is None else json.dumps(body).encode(), headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as exc:
                return exc.code, json.load(exc)

        def ok(name, value):
            checks.append({'name': name, 'passed': bool(value)})
            if not value:
                raise AssertionError(name)

        try:
            code, health = call('/health')
            ok('health is a live observation-only service', code == 200 and health['role'] == 'observation_only' and health['gateway_instance'] == state.session)
            _, snapshot = call('/api/v1/state')
            _, history = call('/api/v1/timeline?after=500')
            ok('empty snapshot/history share the actual state instance', snapshot['gateway_instance'] == history['gateway_instance'] == state.live.instance)
            ok('no fabricated reports or events', snapshot['nodes'] == [] and snapshot['edges'] == [] and history['events'] == [] and snapshot['view_mode'] == 'live' and snapshot['fake_gps'] is False)
            _, status = call('/api/studio/status')
            ok('legacy demo and fake GPS controls are explicitly disabled', status['mode'] == 'live' and status['capabilities']['demo_control'] is False and status['capabilities']['fake_gps_toggle'] is False)
            for path in ('/api/studio/mode', '/api/studio/demo/start', '/api/studio/demo/stop', '/api/studio/demo/replay', '/api/studio/fake-gps', '/api/pc/send'):
                ok('removed control returns 404: ' + path, call(path, {})[0] == 404)
            _, source_list = call('/api/v1/lora/sources')
            ok('isolated source manager has no adapters or sockets', source_list['sources'] == [] and source_list['selected_source_id'] is None and sources.sock is None and sources.thread is None)
            ok('source selection requires same origin', call('/api/v1/lora/sources/select', {'source_id': None}, origin=False)[0] == 403)
            ok('automatic source selection is explicit and empty', call('/api/v1/lora/sources/select', {'source_id': None})[1]['selection'] == 'auto')
            ok('unknown source is rejected', call('/api/v1/lora/sources/select', {'source_id': 'not-registered'})[0] == 400)
            _, topology = call('/api/v1/lora/topology')
            ok('unavailable source never fabricates topology', topology['source'] == 'unavailable' and topology['reports'] == [])
            ok('empty inventory remains empty', call('/api/v1/fleet')[1]['nodes'] == [])
            recovery_code, recovery = call('/api/v1/recovery')
            ok('absent recovery evidence is unknown, not recovered', recovery_code == 503 and recovery['state'] == 'unknown')
            ok('recording requires same origin', call('/api/v1/replay/start', {}, origin=False)[0] == 403)
            first = call('/api/v1/replay/start', {})[1]['id']
            ok('duplicate start preserves the existing session', call('/api/v1/replay/start', {})[1]['id'] == first)
            for _ in range(101):
                replay.sample()
            _, page = call('/api/v1/replay/session?id=' + first + '&offset=100&limit=1')
            ok('real SQLite paginates beyond 100 frames', page['total'] == 101 and page['offset'] == 100 and len(page['frames']) == 1)
            ok('recorded interruption remains unavailable', page['frames'][0]['topology']['source'] == 'unavailable')
            ok('unpaged large session is rejected', call('/api/v1/replay/session?id=' + first)[0] == 413)
            ok('stop returns the closed session identifier', call('/api/v1/replay/stop', {})[1]['id'] == first)
            ok('session remains listed but is no longer active', call('/api/v1/replay/sessions')[1]['active_id'] is None)
        finally:
            server.shutdown()
            thread.join(3)
            server.server_close()
            replay.close()
            sources.close()
            state.close()
            (out / 'CHECK.json').write_text(json.dumps({'checks': checks, 'serial_opens': 0, 'physical_boards': 0, 'production_services_changed': False}, ensure_ascii=False, indent=2), encoding='utf-8')
        reopened = Replay(out / 'isolated-replay.sqlite3', sources.topology, interval=3600)
        try:
            ok('sessions and original timestamps survive DB reopen', reopened.sessions()['sessions'][0]['count'] == 101 and reopened.session(first, 100, 1)['frames'][0]['t_ms'] == page['frames'][0]['t_ms'])
        finally:
            reopened.close()
            (out / 'CHECK.json').write_text(json.dumps({'checks': checks, 'serial_opens': 0, 'physical_boards': 0, 'production_services_changed': False}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'checks': len(checks), 'passed': all(c['passed'] for c in checks), 'physical_boards': 0}))


if __name__ == '__main__':
    main()

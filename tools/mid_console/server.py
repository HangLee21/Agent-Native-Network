"""Loopback-only M-020 console. Device operations belong to H's adapter."""
import argparse
import copy
import importlib
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from state import StateStore, process_alive
import recovery

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
MAX_BODY = 16384
ID = re.compile(r'^[0-9a-f]{24}$')


class RequestError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def validate(q):
    if not isinstance(q, dict):
        raise ValueError('JSON object required')
    allowed = {'src', 'dst', 'mode', 'hops', 'via', 'count', 'model_id', 'node_set', 'graph_edges','payload_hex','request_id'}
    if set(q) - allowed:
        raise ValueError('unknown planning fields')
    if 'payload_hex' in q and (type(q['payload_hex']) is not str or not re.fullmatch(r'(?:[0-9a-fA-F]{2}){0,160}',q['payload_hex'])):
        raise ValueError('payload_hex must encode 0..160 bytes')
    if 'request_id' in q and (type(q['request_id']) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',q['request_id'])):
        raise ValueError('request_id must be 8..64 safe ASCII characters')
    if any(type(q.get(k)) is not str or q[k] not in 'ABCDE' or len(q[k]) != 1 for k in ('src', 'dst')) or q['src'] == q['dst']:
        raise ValueError('choose different A..E endpoints')
    if q.get('mode') not in ('mid', 'hops', 'manual'):
        raise ValueError('mode must be mid/hops/manual')
    if type(q.get('count', 1)) is not int or not 1 <= q.get('count', 1) <= 10:
        raise ValueError('count must be integer 1..10')
    if q['mode'] == 'hops' and (type(q.get('hops')) is not int or not 1 <= q['hops'] <= 4):
        raise ValueError('hops must be integer 1..4')
    if q['mode'] == 'manual':
        via = q.get('via', [])
        if not isinstance(via, list) or len(via) > 3 or any(type(x) is not str or x not in list('ABCDE') for x in via):
            raise ValueError('via must be up to three A..E relays')
        if len(set([q['src'], *via, q['dst']])) != len(via) + 2:
            raise ValueError('manual chain must not repeat nodes')
    if 'node_set' in q and (not isinstance(q['node_set'], list) or any(type(x) is not str or x not in list('ABCDE') for x in q['node_set'])):
        raise ValueError('invalid node_set')
    if 'graph_edges' in q and (not isinstance(q['graph_edges'], list) or len(q['graph_edges']) > 20 or any(not isinstance(e, list) or len(e) != 2 or any(type(x) is not str or x not in list('ABCDE') for x in e) for e in q['graph_edges'])):
        raise ValueError('invalid graph_edges')
    if 'model_id' in q and q['model_id'] != 'assumed-five-v1':
        raise ValueError('unknown model_id')


class Console:
    def __init__(self, hardware=False, state_dir=None):
        self.hardware = hardware
        self.lock = threading.RLock()
        self.planner_lock = threading.Lock()
        self.plans, self.runs = {}, {}
        self.active = None
        self.workers = {}
        self.store = StateStore(state_dir) if state_dir else None
        self.adapter = None
        self.adapter_error = 'H adapter has not been delivered'
        candidate = ROOT / '.local/mid/E1-016/venv/Scripts/python.exe'
        self.python = str(candidate) if candidate.is_file() else sys.executable
        saved = self.store.load() if self.store else None
        if saved:
            self.plans, self.runs, self.active = saved['plans'], saved['runs'], saved['active']
            for record in self.runs.values():
                record['stop_event'] = threading.Event()
                if record.get('worker_running'):
                    record.update(state='cleanup_unconfirmed', error='Previous service worker requires reconciliation')

    def persist(self):
        if self.store:
            self.store.save(self.plans, self.runs, self.active)

    def worker_active(self, rid):
        worker = self.workers.get(rid)
        record = self.runs[rid]
        if worker and worker.is_alive():
            return True
        return record.get('worker_running', False) and process_alive(record.get('owner_pid'))

    def restore_run(self, path):
        """CLI-only migration of an immutable GET snapshot from the old service."""
        path = Path(path).resolve()
        if not path.is_relative_to(ROOT / 'simulation/outputs/E2-018'):
            raise ValueError('restore snapshots must be in E2-018 evidence scope')
        record = json.loads(path.read_text(encoding='utf-8'))
        rid = record['run_id']
        if not ID.fullmatch(rid) or not record.get('finished_at') or record.get('state') != 'cleanup_unconfirmed':
            raise ValueError('only a finished cleanup_unconfirmed snapshot can be migrated')
        output = Path(record['output_directory']).resolve()
        if not output.is_relative_to(ROOT / 'simulation/outputs/H-007'):
            raise ValueError('invalid original H output scope')
        with self.lock:
            if self.active or rid in self.runs:
                raise ValueError('existing state would be overwritten')
            result = record.get('result') or {}
            record.update(stop_event=threading.Event(), worker_running=False,
                          participants=list(result['model']['bindings'].values()),
                          migration=dict(source=str(path), original_plan_available=False))
            chain = result.get('expected_chain') or []
            record['selection'] = dict(mode=result.get('mode'), count=result.get('requested'),
                                       src=chain[0] if chain else None, dst=chain[-1] if chain else None,
                                       hops=len(chain)-1 if chain else None)
            pid = record['plan_id']
            # Preserve the plan ID and known selection as consumed. Never reconstruct an
            # unobserved routing table or reset the old plan into a sendable state.
            self.plans[pid] = dict(plan=None, request=record['selection'], run_id=rid, created=0,
                                   migration_original_plan_unavailable=True)
            self.runs[rid], self.active = record, rid
            self.persist()

    def hardware_status(self, publisher=None):
        if self.adapter is None:
            try:
                self.adapter = importlib.import_module('tools.mid_hardware.console.adapter')
            except ImportError as exc:
                self.adapter_error = str(exc)
        if self.adapter is None:
            try:
                lease = importlib.import_module('tools.mid_hardware.console.lease')
                value = lease.status()
            except ImportError:
                value = dict(busy=False)
            return dict(value, run_available=False, ready_nodes=[], reason=value.get('reason') or self.adapter_error)
        try:
            value = self.adapter.status(**({'publisher': publisher} if publisher else {}))
            if not isinstance(value, dict):
                raise ValueError('H status must be an object')
            if not self.hardware:
                value = dict(value, run_available=False, reason='preview_mode; ' + str(value.get('reason') or 'start with --hardware for explicit H execution'))
            return value
        except Exception as exc:
            return dict(run_available=False, busy=False, ready_nodes=[], reason='H status error: ' + str(exc))

    def status(self):
        live = self.hardware_status()
        with self.lock:
            busy = bool(self.active) or bool(live.get('busy'))
            active_state = self.runs[self.active]['state'] if self.active else None
            reason = ('cleanup_unconfirmed' if active_state == 'cleanup_unconfirmed' else
                      'console_recovering' if active_state == 'recovering' else
                      'console_run_active' if self.active else live.get('reason'))
            return dict(ok=True, service='M-020', mode='hardware' if self.hardware else 'preview',
                        busy=busy, run_available=live.get('run_available') is True and not busy,
                        reason=reason, hardware=live, active_run_id=self.active, active_run_state=active_state,
                        recovery_available=bool(self.hardware and self.active and active_state == 'cleanup_unconfirmed' and
                            not self.worker_active(self.active) and not live.get('busy') and
                            (callable(getattr(self.adapter, 'recover', None)) or recovery.receipt_path(self.active).is_file())),
                        recovery_reason='H_verified_receipt_required' if active_state == 'cleanup_unconfirmed' and not callable(getattr(self.adapter, 'recover', None)) and not recovery.receipt_path(self.active).is_file() else None,
                        process_id=os.getpid(),
                        planner_available=(ROOT / 'tools/mid_baseline/planner/console/plans.py').is_file(),
                        models=[dict(id='assumed-five-v1', label='原五板假设模型（非实时测量）', source_kind='assumption')],
                        limits=dict(count=10, run_seconds=60), rf_started_on_load=False)

    def solve(self, q, live):
        # One bounded worker at a time. Solver stdout never becomes an HTTP stream.
        if not self.planner_lock.acquire(blocking=False):
            raise RequestError(409, 'planner_busy', 'another plan is being solved')
        try:
            proc = subprocess.run([self.python, str(HERE / 'worker.py')],
                input=json.dumps(dict(request=q, available_nodes=live.get('ready_nodes') or None, live_status=live)),
                text=True, encoding='utf-8', capture_output=True, cwd=str(ROOT), timeout=30,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if proc.returncode:
                raise RequestError(503, 'planner_unavailable', 'planner failed: ' + proc.stderr[-1200:])
            plan = json.loads(proc.stdout)
            if not plan.get('ok'):
                err = plan.get('error', {})
                raise RequestError(422, err.get('code', 'plan_failed'), err.get('message', 'plan failed'))
            return plan
        except subprocess.TimeoutExpired:
            raise RequestError(504, 'planner_timeout', 'planning exceeded 30 seconds')
        except (ValueError, OSError) as exc:
            raise RequestError(503, 'planner_unavailable', str(exc))
        finally:
            self.planner_lock.release()

    def plan(self, q):
        validate(q)
        def existing():
            for entry in self.plans.values():
                if q.get('request_id') and entry['request'].get('request_id')==q['request_id']:
                    if entry['request']!=q:raise RequestError(409,'request_conflict','request_id already binds different target or payload')
                    return copy.deepcopy(entry['plan'])
        with self.lock:
            previous=existing()
            if previous:return previous
        live = self.hardware_status(q['src'])
        result = self.solve({k:v for k,v in q.items() if k not in ['payload_hex','request_id']}, live)
        # H starts every node in network_update, even an unused table participant.
        # Its preflight therefore requires the full selected table, not only the chain.
        if not set(result['node_set']) <= set(live.get('ready_nodes', [])):
            result['availability']['runnable'] = False
            result['availability']['reasons'].append('selected_table_nodes_not_ready')
        pid = secrets.token_hex(12)
        result.update(plan_id=pid, run_available=result.get('availability', {}).get('runnable') is True and self.hardware,
                      busy=bool(live.get('busy')), preview=True)
        if 'payload_hex' in q:result['payload_hex']=q['payload_hex'].lower()
        if 'request_id' in q:result['request_id']=q['request_id']
        with self.lock:
            previous=existing()
            if previous:return previous
            if len(self.plans) >= 64:
                oldest = next((key for key,entry in self.plans.items() if not entry['request'].get('request_id')),None)
                if oldest is None:raise RequestError(409,'request_history_full','retained message request history is full; existing request IDs remain valid')
                del self.plans[oldest]
            self.plans[pid] = dict(request=copy.deepcopy(q), plan=copy.deepcopy(result), created=time.monotonic(), run_id=None)
            self.persist()
        return result

    def run(self, pid):
        with self.lock:
            entry = self.plans.get(pid)
            if entry is None:
                raise RequestError(404, 'unknown_plan', 'plan not found; preview again')
            if entry['run_id']:
                return self.public_run(entry['run_id'])
            if self.active:
                raise RequestError(409, 'busy', 'another console run is active')
            if time.monotonic() - entry['created'] > 600:
                raise RequestError(409, 'stale_plan', 'plan expired; preview again')
            live = self.hardware_status(entry['plan']['src'])
            if not self.hardware or live.get('busy') or live.get('run_available') is not True:
                raise RequestError(409, 'hardware_unavailable', live.get('reason') or 'H hardware is not available')
            plan = entry['plan']
            if not set(plan['node_set']) <= set(live.get('ready_nodes', [])):
                raise RequestError(409, 'nodes_not_ready', 'required boards are not currently ready')
            publisher = live.get('publisher')
            boot = live.get('publisher_boot')
            if publisher not in plan['node_set'] or publisher not in live.get('ready_nodes', []) or type(boot) is not int or not 1 <= boot <= 0xffffffff:
                raise RequestError(409, 'publisher_unknown', 'current publisher binding is not valid')
            if not callable(getattr(self.adapter, 'execute', None)):
                raise RequestError(503, 'adapter_contract', 'H execute interface is not available')
            rid = secrets.token_hex(12)
            stop = threading.Event()
            self.runs[rid] = dict(ok=True, run_id=rid, plan_id=pid, state='running', events=[], result=None,
                                  rf_measured=None, started_at=time.time(), stop_event=stop, owner_pid=os.getpid(),
                                  worker_running=True, participants=plan['network_update']['nodes'], plan_snapshot=copy.deepcopy(plan))
            entry['run_id'], self.active = rid, rid
            self.persist()
            worker = threading.Thread(target=self.execute, args=(rid, copy.deepcopy(plan), stop), daemon=False)
            self.workers[rid] = worker
            worker.start()
            return self.public_run(rid)

    def execute(self, rid, plan, stop):
        timer = threading.Timer(60, stop.set)
        timer.daemon = True
        timer.start()
        def emit(event):
            with self.lock:
                events = self.runs[rid]['events']
                if len(events) < 2000:
                    events.append(copy.deepcopy(event))
        try:
            # H allocates its own output directory/lease and performs final device checks.
            output = ROOT / 'simulation/outputs/H-007' / (time.strftime('%Y%m%d-%H%M%S') + '-console-' + rid)
            with self.lock:
                self.runs[rid]['output_directory'] = str(output)
                self.persist()
            result = self.adapter.execute(plan, output, stop, on_event=emit, timeout=60)
            with self.lock:
                self.runs[rid].update(state=result.get('status', 'failed'), result=result,
                                      evidence_kind=result.get('evidence_kind'), output_directory=str(output))
                confirmations = result.get('stop_confirmed', {})
                participants = plan['network_update']['nodes']
                drained = result.get('all_ports_closed') is True and all(confirmations.get(node) is True for node in participants)
                proof = result.get('cleanup_proof')
                if proof and self.valid_proof(proof, rid, participants):
                    drained = True
                    self.runs[rid]['cleanup_proof'] = proof
                self.runs[rid]['cleanup_confirmed'] = drained
                if not drained:
                    self.runs[rid].update(state='cleanup_unconfirmed', error='H must verify stop/drain before another run')
        except Exception as exc:
            with self.lock:
                self.runs[rid].update(state='cleanup_unconfirmed', error=str(exc), cleanup_confirmed=False)
        finally:
            timer.cancel()
            with self.lock:
                self.runs[rid]['finished_at'] = time.time()
                self.runs[rid]['worker_running'] = False
                if self.active == rid and self.runs[rid].get('cleanup_confirmed') is True:
                    self.active = None
                # Only finished records can be evicted; active leases are never dropped.
                while len(self.runs) > 100:
                    del self.runs[next(iter(self.runs))]
                self.persist()

    @staticmethod
    def valid_proof(proof, rid, participants):
        if not isinstance(proof, dict) or proof.get('run_id') != rid or proof.get('safe_to_release') is not True or proof.get('all_ports_closed') is not True:
            return False
        if proof.get('kind') == 'confirmed_stopped':
            return all(proof.get('stop_confirmed', {}).get(node) is True for node in participants)
        return (proof.get('kind') == 'prestart_no_side_effects' and proof.get('effects_started') is False
                and proof.get('proof_complete') is True)

    def recover(self, rid):
        with self.lock:
            if rid not in self.runs:
                raise RequestError(404, 'unknown_run', 'run not found')
            record = self.runs[rid]
            if record.get('recovery', {}).get('status') == 'released':
                return self.public_run(rid)
            if self.active != rid:
                raise RequestError(409, 'not_active_failure', 'recovery targets only the current failed run')
            if record['state'] == 'recovering':
                return self.public_run(rid)
            if record['state'] != 'cleanup_unconfirmed' or self.worker_active(rid):
                raise RequestError(409, 'worker_not_finished', 'wait for the original worker to finish')
            live = self.hardware_status()
            if live.get('busy'):
                raise RequestError(409, 'hardware_busy', live.get('reason') or 'hardware owner is busy')
            if not self.hardware:
                raise RequestError(503, 'recovery_unavailable', 'H recovery adapter is not available')
            if not callable(getattr(self.adapter, 'recover', None)) and not recovery.receipt_path(rid).is_file():
                raise RequestError(409, 'recovery_evidence_pending', 'H must provide fresh verified stop evidence first')
            token = secrets.token_hex(12)
            stop = threading.Event()
            record.update(state='recovering', recovery_token=token, worker_running=True, owner_pid=os.getpid())
            record['stop_event'] = stop
            record['recovery'] = dict(status='checking', token=token, started_at=time.time())
            self.persist()
            snapshot = {k: copy.deepcopy(v) for k, v in record.items() if k != 'stop_event'}
            worker = threading.Thread(target=self.reconcile, args=(rid, token, snapshot, stop), daemon=False)
            self.workers[rid] = worker
            worker.start()
            return self.public_run(rid)

    def reconcile(self, rid, token, snapshot, stop):
        output = ROOT / 'simulation/outputs/H-007' / (time.strftime('%Y%m%d-%H%M%S') + '-recovery-' + rid + '-' + token)
        timer = threading.Timer(30, stop.set)
        timer.daemon = True
        timer.start()
        proof = None
        error = None
        try:
            recover = getattr(self.adapter, 'recover', None) or recovery.recover
            proof = recover(snapshot, output, stop, timeout=30)
        except Exception as exc:
            error = str(exc)
        finally:
            timer.cancel()
            with self.lock:
                record = self.runs[rid]
                # A stale completion can never clear or overwrite a newer operation.
                if record.get('recovery_token') != token:
                    return
                valid = self.valid_proof(proof, rid, record.get('participants', [])) and bool(record.get('participants'))
                audit = dict(token=token, finished_at=time.time(), proof=proof, error=error,
                             status='released' if valid and self.active == rid else 'not_released', output_directory=str(output))
                record.setdefault('recovery_history', []).append(audit)
                record.update(recovery=audit, worker_running=False)
                if valid and self.active == rid:
                    record.update(state='failed', cleanup_confirmed=True)
                    self.active = None
                else:
                    record['state'] = 'cleanup_unconfirmed'
                self.persist()

    def public_run(self, rid):
        with self.lock:
            if rid not in self.runs:
                raise RequestError(404, 'unknown_run', 'run not found')
            record = copy.deepcopy({k: v for k, v in self.runs[rid].items() if k != 'stop_event'})
        result = record.get('result') or {}
        packets = copy.deepcopy(result.get('packets', []))
        for packet in packets:
            identity = packet.get('identity')
            valid_identity = isinstance(identity, list) and len(identity) == 4
            if valid_identity:
                packet.update(zip(('origin', 'origin_boot', 'seq', 'dst'), identity))
            delivered = packet.get('destination_received') is True
            packet['delivered'] = delivered
            packet['status'] = 'destination_rx_local' if delivered else 'unconfirmed'
            # Infer no chain from a plan. Only an unambiguous complete set of observed
            # source TX / relay RX+TX / destination RX can be drawn as an actual path.
            actual = []
            if delivered and valid_identity:
                next_hops = {}
                for edge in packet.get('actual_edges', []):
                    next_hops.setdefault(edge['node'], set()).add(edge['next_hop'])
                current = packet['origin']
                actual = [current]
                while current != packet['dst'] and len(actual) <= 5:
                    candidates = next_hops.get(current, set())
                    if len(candidates) != 1 or (current != packet['origin'] and current not in packet.get('relays', [])):
                        actual = []
                        break
                    current = next(iter(candidates))
                    if current in actual:
                        actual = []
                        break
                    actual.append(current)
                if not actual or actual[-1] != packet['dst']:
                    actual = []
            packet['actual_path'] = actual or None
        record['packets'] = packets
        record['summary'] = dict(evidence_kind=result.get('evidence_kind'),
            accepted=sum(p.get('command_result', {}).get('ok') is True for p in packets if p.get('command_result')),
            received=result.get('destination_unique_received'),
            unconfirmed=max(0, result.get('requested', len(packets)) - result.get('destination_unique_received', 0)))
        return record

    def stop(self, rid):
        with self.lock:
            if rid not in self.runs:
                raise RequestError(404, 'unknown_run', 'run not found')
            record = self.runs[rid]
            if record['state'] in ('running', 'stopping'):
                record['state'] = 'stopping'
                record['stop_event'].set()
            elif record['state'] == 'cleanup_unconfirmed':
                record['stop_event'].set()
            elif record['state'] == 'recovering':
                record['stop_event'].set()
            self.persist()
            return self.public_run(rid)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def guard(self, write=False):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host = self.headers.get('Host')
        if len(self.headers.get_all('Host', [])) != 1 or host not in hosts:
            raise RequestError(403, 'invalid_host', 'loopback Host required')
        origin = self.headers.get('Origin')
        if len(self.headers.get_all('Origin', [])) > 1 or (write or origin is not None) and origin != 'http://' + host:
            raise RequestError(403, 'invalid_origin', 'same-origin request required')
        if write and self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise RequestError(403, 'cross_site', 'cross-site request rejected')

    def body(self):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('transfer encoding unsupported')
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise ValueError('application/json required')
        n = int(self.headers.get('Content-Length', '0'))
        if not 0 < n <= MAX_BODY:
            raise ValueError('request body must be 1..16384 bytes')
        data = json.loads(self.rfile.read(n).decode('utf-8'), object_pairs_hook=strict_object,
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError('non-finite JSON')))
        if not isinstance(data, dict):
            raise ValueError('JSON object required')
        return data

    def reply(self, status, value, kind='application/json; charset=utf-8'):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8') if not isinstance(value, bytes) else value
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def handle_request(self, write):
        try:
            self.connection.settimeout(10)
            self.guard(write)
            path = urlsplit(self.path).path
            app = self.server.console
            if not write and path == '/api/status':
                return self.reply(200, app.status())
            parts = path.strip('/').split('/')
            if len(parts) >= 3 and parts[:2] == ['api', 'runs'] and ID.fullmatch(parts[2]):
                if not write and len(parts) == 3:
                    return self.reply(200, app.public_run(parts[2]))
                if write and len(parts) == 4 and parts[3] == 'stop':
                    if self.body():
                        raise ValueError('stop expects {}')
                    return self.reply(200, app.stop(parts[2]))
                if write and len(parts) == 4 and parts[3] == 'recover':
                    if self.body():
                        raise ValueError('recover expects {}; clients cannot supply proof or paths')
                    return self.reply(202, app.recover(parts[2]))
            if write and path == '/api/plan':
                return self.reply(200, app.plan(self.body()))
            if write and path == '/api/run':
                q = self.body()
                if set(q) != {'plan_id'} or type(q['plan_id']) is not str or not ID.fullmatch(q['plan_id']):
                    raise ValueError('valid plan_id required')
                return self.reply(202, app.run(q['plan_id']))
            if write or path.startswith('/api/'):
                raise RequestError(404, 'not_found', 'endpoint not found')
            if path == '/recovery/':
                return self.reply(200, (HERE/'static/recovery.html').read_bytes(), 'text/html; charset=utf-8')
            return self.static(path)
        except RequestError as exc:
            self.reply(exc.status, dict(ok=False, error=dict(code=exc.code, message=exc.message)))
        except (ValueError, UnicodeError) as exc:
            self.reply(400, dict(ok=False, error=dict(code='invalid_request', message=str(exc))))
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            self.reply(500, dict(ok=False, error=dict(code='internal_error', message='service error; see local console')))
            import traceback
            traceback.print_exc()

    def static(self, path):
        demo = ROOT / 'research/agent_native_network/mid_replacement_demo'
        if path.startswith('/replay/'):
            base, relative = demo, path[len('/replay/'): ] or 'index.html'
        else:
            base, relative = demo / 'control', path.lstrip('/') or 'index.html'
            if not (base / 'index.html').is_file():
                base = HERE / 'static'
        base = base.resolve()
        target = (base / unquote(relative)).resolve()
        if not target.is_relative_to(base) or target.suffix not in {'.html', '.css', '.js', '.json', '.svg', '.png', '.ico'} or not target.is_file():
            raise RequestError(404, 'not_found', 'asset not found')
        self.reply(200, target.read_bytes(), (mimetypes.guess_type(target.name)[0] or 'application/octet-stream') + ('; charset=utf-8' if target.suffix in {'.html', '.css', '.js', '.json'} else ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--hardware', action='store_true', help='enable H adapter; never opens devices on page load')
    parser.add_argument('--open', action='store_true', help='open default browser')
    parser.add_argument('--restore-run', help='CLI-only import of an archived finished cleanup failure')
    parser.add_argument('--state-dir', help='CLI-only retained state directory within E2 scope')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be 1024..65535')
    state_dir = Path(args.state_dir).resolve() if args.state_dir else ROOT / '.local/mid/E2-018' / ('service-' + str(args.port))
    if not (state_dir.is_relative_to(ROOT/'.local/mid/E2-018') or state_dir.is_relative_to(ROOT/'simulation/outputs/E2-018')):
        parser.error('state directory must stay within E2-018 scope')
    marker = ROOT/'.local/mid/E2-018'/('migration-required-'+str(args.port)+'.json')
    if marker.exists() and not (state_dir/'state.json').is_file() and not args.restore_run:
        parser.error('Existing cleanup failure requires retained-state migration; see tools/mid_console/MIGRATION_PLAN.md')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.daemon_threads = True
    server.console = Console(args.hardware, state_dir)
    if args.restore_run:
        server.console.restore_run(args.restore_run)
    url = f'http://127.0.0.1:{args.port}/'
    print(f'M-020 console: {url} ({"hardware enabled" if args.hardware else "preview only"})', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        with server.console.lock:
            if server.console.active:
                server.console.stop(server.console.active)
        print('Stop requested; H retains its lease until device drain completes.', flush=True)
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

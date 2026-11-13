"""Read H's fixed-path stop-only receipt. Never opens a device or sends a command."""
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAC_A = '90:da:72:48:a4:f8'


def receipt_path(rid):
    return ROOT / '.local/mid/H-007/recoveries' / (rid + '.json')


def validate_receipt(record, receipt, *, now=None, read_bytes=None):
    read_bytes = read_bytes or (lambda path: path.read_bytes())
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if (receipt.get('schema') != 'mid.console.cleanup_recovery.v1' or
            receipt.get('run_id') != record['run_id'] or receipt.get('status') != 'verified_stop_only' or
            receipt.get('original_failure_retained') is not True or receipt.get('automatic_business_resend') is not False or
            receipt.get('all_ports_closed') is not True):
        raise ValueError('H receipt schema, identity or safety flags invalid')
    participants = record['participants']
    if not participants or any(receipt.get('stop_confirmed', {}).get(n) is not True for n in participants):
        raise ValueError('not all participants have stop confirmation')
    expected_old = Path(record['output_directory']).resolve() / 'result.json'
    source_objects = {}
    for ref in receipt.get('sources', []):
        path = Path(ref['path']).resolve()
        if not path.is_relative_to(ROOT / 'simulation/outputs/H-007') or path in source_objects:
            raise ValueError('H evidence source scope/duplicate invalid')
        raw = read_bytes(path)
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('H source hash mismatch')
        source_objects[path] = json.loads(raw)
    if len(source_objects) != 2 or expected_old not in source_objects:
        raise ValueError('receipt must bind this exact original failure')
    old = source_objects.pop(expected_old)
    current = next(iter(source_objects.values()))
    if old != record.get('result'):
        raise ValueError('original failure result does not match service snapshot')
    if old.get('all_ports_closed') is not True or any(old.get('stop_confirmed', {}).get(n) is not True for n in participants if n != MAC_A):
        raise ValueError('original other-board stop proof incomplete')
    if not all(current.get(k) is True for k in ('success', 'closed', 'stop_confirmed')):
        raise ValueError('new A recovery did not finish safely')
    info, stats = current['info'], current['stats']
    if info.get('node_id') != MAC_A or stats.get('node_id') != MAC_A or info.get('device_label') != 'A':
        raise ValueError('A identity mismatch')
    if info.get('boot_id') != stats.get('boot_id') or info.get('build_id') != stats.get('build_id') or type(info.get('boot_id')) is not int:
        raise ValueError('A boot/build mismatch')
    if info.get('uart_baud') != 460800 or stats.get('uart_baud') != 460800 or stats.get('mode') != 'idle' or stats.get('queue_depth') != 0:
        raise ValueError('A current state not idle at expected baud')
    if any(stats.get(k) is not False for k in ('radio', 'stopping', 'locked_until_reset')):
        raise ValueError('A radio/drain unconfirmed')
    if receipt.get('verified_at') != current.get('finished_at'):
        raise ValueError('receipt timestamp does not bind source')
    age = (now - datetime.datetime.fromisoformat(current['finished_at'])).total_seconds()
    if not 0 <= age <= 300:
        raise ValueError('H physical evidence expired; fresh receipt required')
    if datetime.datetime.fromisoformat(current['finished_at']).timestamp() < record.get('finished_at', 0):
        raise ValueError('A evidence predates the failed worker completion')
    expected_A = dict(mac=MAC_A, boot=info['boot_id'], build=info['build_id'], uart_baud=460800, mode='idle', queue_depth=0)
    if receipt.get('actual_A') != expected_A:
        raise ValueError('receipt A summary does not match physical source')
    return dict(run_id=record['run_id'], safe_to_release=True, kind='confirmed_stopped',
                all_ports_closed=True, stop_confirmed=receipt['stop_confirmed'], verified_at=receipt['verified_at'],
                sources=receipt['sources'], original_failure_retained=True, automatic_business_resend=False)


def recover(record, output, stop_event, timeout=30):
    if stop_event.is_set():
        raise RuntimeError('recovery cancelled')
    path = receipt_path(record['run_id'])
    from tools.mid_hardware.console.lease import HardwareLease
    with HardwareLease('H007-reconcile'):
        raw = path.read_bytes()
        receipt = json.loads(raw.decode('utf-8-sig'))
        proof = validate_receipt(record, receipt)
        proof['receipt_source'] = dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())
    return proof

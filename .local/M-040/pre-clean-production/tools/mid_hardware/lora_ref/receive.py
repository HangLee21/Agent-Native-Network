"""Bounded A-to-PC LoRa JSONL capture; binary decoding belongs to E1-029."""
import argparse
import contextlib
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
CODEC = ROOT/'firmware/mid_baseline/field_agent/lora_ref/decoder.py'
# Default gateway is the board used for the first H-019 pilot. The LRN1 frame has
# no destination field, so the gateway is whoever is configured as role=rx on the
# same PHY; its identity is stamped on the receiver side. A real gateway or a
# different board therefore has to be named explicitly with --gateway-mac, or
# accepted provisionally with --any-gateway. See GATEWAY_SWAP.md.
DEFAULT_GATEWAY = '90:da:72:48:a4:f8'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--input', type=Path, help='Decode a saved JSONL file without opening any device')
    mode.add_argument('--port', help='Explicit later hardware capture; no device command is sent')
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gateway-mac', default=DEFAULT_GATEWAY,
                        help='Expected role=rx board MAC (default: H-019 pilot board A)')
    parser.add_argument('--any-gateway', action='store_true',
                        help='Accept any role=rx board and record the observed set; use while migrating')
    parser.add_argument('--task-id', choices=['H-019','H-020','H-021','H-022'], default='H-019')
    args = parser.parse_args()
    out = args.output.resolve()
    scope = (ROOT/'simulation/outputs'/args.task_id).resolve()
    if not out.is_relative_to(scope) or not 0 < args.duration <= 600:
        parser.error(f'New {args.task_id} output and duration 0..600 required')
    expected = None if args.any_gateway else args.gateway_mac.strip().lower()
    if expected is not None and not re.fullmatch(r'[0-9a-f]{2}(?::[0-9a-f]{2}){5}', expected):
        parser.error('--gateway-mac must be six colon-separated hex octets')
    if args.input and args.input.stat().st_size > 16*1024*1024:
        parser.error('Saved input exceeds 16 MiB')
    if not CODEC.is_file():
        parser.error('E1-029 decoder has not been handed over')
    codec_hash = hashlib.sha256(CODEC.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location('e1_lrn1_decoder', CODEC)
    codec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codec)
    out.mkdir(parents=True, exist_ok=False)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    summary = dict(decoded=0, unique_reports=0, duplicates=0, ignored=0, errors=[],
        serial_opens=0, device_commands=0, flash_writes=0, service_restarts=0,
        input_kind='saved_file' if args.input else 'serial_RX_envelope',
        gateway_mac_expected=expected, gateway_ids=[],
        gateway_swapped=expected not in (None, DEFAULT_GATEWAY), task_id=args.task_id,
        decoder=str(CODEC), decoder_sha256=codec_hash, actual_RF_validated=False)
    if args.input:
        summary['input_path'] = str(args.input.resolve())
        summary['input_sha256'] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    seen, last_seq = {}, {}
    try:
        with contextlib.ExitStack() as stack:
            if args.input:
                source = stack.enter_context(args.input.open('rb'))
            else:
                from tools.mid_hardware.console.lease import HardwareLease
                import serial
                stack.enter_context(HardwareLease('H019'))
                wire = serial.Serial(port=None, baudrate=460800, timeout=.2, write_timeout=1)
                wire.dtr = wire.rts = False
                wire.port = args.port
                wire.open()
                summary['serial_opens'] = 1
                source = stack.enter_context(wire)
            journal = stack.enter_context((out/'reports.jsonl').open('x', encoding='utf-8'))
            end = time.monotonic()+args.duration
            for index in range(4096):
                if time.monotonic() >= end:
                    summary['bounded_end'] = 'duration'
                    break
                raw = source.read(2049) if args.input and args.input.suffix.lower()=='.json' else source.readline(2049)
                if not raw:
                    if args.input:
                        break
                    continue
                if len(raw) > 2048 or not raw.endswith(b'\n') and not args.input:
                    raise ValueError('Oversized or incomplete serial line; capture stopped')
                try:
                    line = raw.decode('utf-8-sig')
                    try:
                        hint = json.loads(line)
                    except json.JSONDecodeError:
                        summary['ignored'] += 1
                        continue
                    if not isinstance(hint, dict) or hint.get('schema') != 'lora.ref.v1' or hint.get('event') != 'lora_ref_rx':
                        summary['ignored'] += 1
                        continue
                    event = codec.decode_serial_line(line)
                    gateway = str(event['gateway_id']).lower()
                    if expected is not None and gateway != expected:
                        raise ValueError(f'RX gateway {gateway} is not the expected {expected}')
                    if gateway not in summary['gateway_ids']:
                        summary['gateway_ids'].append(gateway)
                    report = event['report']
                    key = report['observer_id'], report['observer_boot'], report['report_seq']
                    frame = event['frame_hex'].lower()
                    duplicate = key in seen
                    if duplicate and seen[key] != frame:
                        raise ValueError('Same report identity has different frame bytes')
                    previous = last_seq.get(key[:2])
                    gap = max(0, key[2]-previous-1) if previous is not None else None
                    last_seq[key[:2]] = max(key[2], previous or key[2])
                    seen[key] = frame
                    summary['decoded'] += 1
                    summary['duplicates'] += int(duplicate)
                    summary['unique_reports'] += int(not duplicate)
                    row = dict(pc_received_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        pc_received_monotonic_ns=time.monotonic_ns(), raw_serial_line=line.rstrip('\r\n'),
                        decoded=event, duplicate=duplicate, sequence_gap=gap,
                        observation_scope='state_at_source_snapshot', renew_wifi_mutual=False,
                        input_kind=summary['input_kind'])
                    journal.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
                    journal.flush()
                except (ValueError, KeyError, TypeError) as exc:
                    summary['errors'].append(dict(line=index+1, error=str(exc)))
                    if args.port:
                        raise
    except Exception as exc:
        summary['fatal_error'] = repr(exc)
    summary.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        all_ports_closed=True, decoder_unchanged=hashlib.sha256(CODEC.read_bytes()).hexdigest()==codec_hash)
    (out/'RESULT.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
    manifest.update(template_only=False, task_id=args.task_id, run_id=out.name, started_at=started,
        finished_at=summary['finished_at'], worktree=str(ROOT), output_directory=str(out),
        command=[sys.executable,*sys.argv], python_executable=sys.executable,
        dirty_files_sha256={str(CODEC.relative_to(ROOT)):codec_hash,
            str(Path(__file__).relative_to(ROOT)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        status='decode_saved', limitations=['Saved files and synthetic fixtures do not prove physical LoRa reception.',
            'USB envelope identity is checked; no flash, configuration, board command or live-map mutation.'])
    (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(summary))
    if summary['errors'] or summary.get('fatal_error') or not summary['decoder_unchanged']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

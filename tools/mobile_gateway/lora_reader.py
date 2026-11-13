"""Studio-owned passive LoRa gateway reader.

The gateway is *discovered*, never hard-coded: this process may be pointed at an
explicit serial port, or it scans the serial devices once and adopts whichever one
first emits a `lora.ref.v1` receive envelope. The adopted identity (gateway MAC,
port, USB location) is persisted so later starts are deterministic, and every
adoption is reported upstream with the evidence it was based on.

Nothing is ever written to the device: the port is opened read-only, no command is
sent, and stdin EOF releases the serial and the hardware lease.
"""
import argparse
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

from tools.mid_edge.lora import decoder

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / '.local/mid/H-020/gateway.json'
SCHEMA = 'lora.ref.v1'


def emit(**value):
    print(json.dumps(value, allow_nan=False), flush=True)


def load_config(path):
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or not doc.get('port'):
        return None
    return doc


def save_config(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def ch340_ports():
    from serial.tools.list_ports import comports
    return [p for p in comports() if p.vid == 0x1a86 and p.pid == 0x7523]


def port_present(port):
    """Any serial device counts: a dedicated gateway need not be a CH340 board."""
    from serial.tools.list_ports import comports
    return any(p.device == port for p in comports())


def probe(port, seconds):
    """Read passively until one receive envelope appears; returns its gateway identity."""
    import serial
    wire = serial.Serial(port=None, baudrate=460800, timeout=.2)
    wire.dtr = wire.rts = False
    wire.port = port
    deadline = time.monotonic() + seconds
    buffer = bytearray()
    try:
        with wire:
            wire.reset_input_buffer()
            while time.monotonic() < deadline:
                buffer.extend(wire.read(min(max(wire.in_waiting, 1), 4096)))
                while b'\n' in buffer:
                    raw, _, rest = buffer.partition(b'\n')
                    buffer = bytearray(rest)
                    if len(raw) > 2048:
                        continue
                    try:
                        hint = json.loads(raw.decode('utf-8'))
                    except (ValueError, UnicodeError):
                        continue
                    if not isinstance(hint, dict) or hint.get('schema') != SCHEMA \
                            or hint.get('event') != 'lora_ref_rx':
                        continue
                    return dict(gateway_id=hint.get('gateway_id'),
                                gateway_boot=hint.get('gateway_boot'),
                                first_line_sha256=hashlib.sha256(raw).hexdigest())
                if len(buffer) > 2048:
                    buffer.clear()
    except (OSError, serial.SerialException):
        return None
    return None


def stream(port, stop, accept_gateway, adopted):
    """Forward every decoded frame; a gateway identity change is reported, not fatal."""
    import serial
    wire = serial.Serial(port=None, baudrate=460800, timeout=.2)
    wire.dtr = wire.rts = False
    wire.port = port
    with wire:
        wire.reset_input_buffer()
        emit(kind='status', state='connecting', port=port, error=None, serial_open=True)
        codec, buffer, discarding = decoder(), bytearray(), False
        started = last_frame = time.monotonic()
        while not stop.is_set():
            buffer.extend(wire.read(min(max(wire.in_waiting, 1), 4096)))
            while b'\n' in buffer:
                raw, _, rest = buffer.partition(b'\n')
                buffer = bytearray(rest)
                if discarding or len(raw) > 2048:
                    discarding = False
                    continue
                try:
                    line = raw.decode('utf-8')
                    hint = json.loads(line)
                    if not isinstance(hint, dict) or hint.get('schema') != SCHEMA \
                            or hint.get('event') != 'lora_ref_rx':
                        continue
                    event = codec.decode_serial_line(line)
                    seen = event['gateway_id']
                    if accept_gateway and seen != accept_gateway:
                        emit(kind='status', state='error',
                             error='串口收到的网关身份是 %s，不是指定的 %s' % (seen, accept_gateway))
                        return
                    if seen != adopted['gateway_id']:
                        adopted['gateway_id'] = seen
                        emit(kind='status', gateway_swapped=True, gateway_id=seen)
                    emit(kind='report', event=event)
                    last_frame = time.monotonic()
                except (ValueError, UnicodeError, KeyError, TypeError) as exc:
                    emit(kind='rejected', error=str(exc))
            if len(buffer) > 2048:
                buffer.clear()
                discarding = True
            if time.monotonic() - max(started, last_frame) > 35:
                emit(kind='status', state='unavailable',
                     error='35 秒没有收到网关的有效 LoRa 帧，关闭后重连')
                return


def resolve(args):
    """Return (port, adoption): explicit port, then the persisted gateway, then a scan."""
    if args.port:
        found = probe(args.port, args.probe_seconds) if not args.gateway_mac else None
        return args.port, found
    saved = load_config(Path(args.config))
    if saved and port_present(saved['port']):
        return saved['port'], dict(saved, reused=True)      # same device still plugged in
    if not args.discovery:
        return (saved or {}).get('port'), None
    for candidate in ch340_ports():
        found = probe(candidate.device, args.probe_seconds)
        if found:
            found.update(port=candidate.device, location=candidate.location,
                         vid=candidate.vid, pid=candidate.pid,
                         adopted_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
            return candidate.device, found
    return None, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', help='explicit serial port; skips discovery')
    p.add_argument('--gateway-mac', help='pin the expected gateway identity')
    p.add_argument('--config', default=str(CONFIG))
    p.add_argument('--no-discovery', dest='discovery', action='store_false', default=True)
    p.add_argument('--probe-seconds', type=float, default=2.5)
    args = p.parse_args()

    from tools.mid_hardware.console.lease import HardwareLease, Busy
    stop = threading.Event()

    def lifetime():
        sys.stdin.readline()
        stop.set()

    threading.Thread(target=lifetime, daemon=True).start()
    try:
        with HardwareLease('H020-Studio-LoRa'):
            port, adoption = resolve(args)
            if not port:
                emit(kind='status', state='unavailable',
                     error='没有发现 LoRa 网关：没有串口设备发出 lora.ref.v1 接收帧',
                     scanned=[(c.device, c.location) for c in ch340_ports()])
                return
            if adoption:
                emit(kind='status', state='adopted', port=port,
                     gateway_id=adoption.get('gateway_id'),
                     gateway_boot=adoption.get('gateway_boot'),
                     adopted_at=adoption.get('adopted_at'),
                     reused=bool(adoption.get('reused')))
                if not adoption.get('reused'):
                    save_config(Path(args.config), adoption)
            adopted = dict(gateway_id=(adoption or {}).get('gateway_id'))
            stream(port, stop, args.gateway_mac, adopted)
    except Busy as exc:
        emit(kind='status', state='busy', error=str(exc))
    except (OSError, Exception) as exc:  # serial errors and lease failures both end the reader
        emit(kind='status', state='unavailable', error=str(exc))


if __name__ == '__main__':
    main()

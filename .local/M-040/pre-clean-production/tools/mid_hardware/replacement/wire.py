"""Single-owner asynchronous serial logging; no firmware reset or data retry."""
import json
import hashlib
import time
import sys
from pathlib import Path
import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools/mid_hardware/console'))
from lease import HardwareLease

class Wire:
    def __init__(self, output, labels, owner='H006'):
        self.out = Path(output)
        self.labels = labels
        self.ports, self.raw, self.buffers, self.tx = {}, {}, {}, {}
        self.pending, self.replies, self.events = {}, {}, []
        self.port_errors = {}
        self.reply_sources, self.metadata, self.line = {}, {}, 0
        self.log = (self.out/'native.jsonl').open('x', encoding='utf-8')
        self.lease = None
        bindings = json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']
        inventory = list(list_ports.comports())
        try:
            self.lease = HardwareLease(owner)
            self.lease.__enter__()
            for label, mac in labels.items():
                b = next(x for x in bindings if x['node_id'] == mac)
                assert len([p for p in inventory if p.device == b['port'] and p.vid == b['vid'] and p.pid == b['pid'] and p.location == b['location']]) == 1
                p = serial.Serial(port=None, baudrate=b.get('runtime_uart_baud',115200), timeout=0, write_timeout=.1)
                p.dtr = p.rts = False
                p.port = b['port']
                p.open()
                self.ports[mac] = p
                self.raw[mac] = (self.out/(label+'.raw.bin')).open('xb')
                self.buffers[mac], self.tx[mac] = bytearray(), []
        except Exception:
            self.close()
            raise

    def record(self, obj):
        self.line += 1
        obj = dict(self.metadata, **obj, host_monotonic_ns=time.monotonic_ns(), capture_line=self.line)
        obj.setdefault('kind', obj.get('direction'))
        obj.setdefault('source', 'hardware_serial' if obj.get('direction') == 'device_rx' else 'H_controller')
        self.log.write(json.dumps(obj)+'\n')
        self.log.flush()
        return obj

    def submit(self, mac, command, role='control'):
        nonce = command['nonce']
        assert nonce not in self.pending
        self.record(dict(direction='host_enqueue', node_id=mac, command=command, role=role))
        if len(self.tx[mac]) >= 16:
            self.record(dict(direction='host_failure', node_id=mac, nonce=nonce, reason='host_tx_queue_full'))
            return False
        wire = (json.dumps(command, separators=(',', ':'))+'\n').encode()
        self.tx[mac].append(dict(wire=wire, offset=0, next_at=0, nonce=nonce, command=command))
        self.pending[nonce] = dict(node=mac, command=command, sent_at=None, expired=False)
        return True

    def poll(self, ignore_port_errors=False):
        now = time.monotonic()
        for mac, p in self.ports.items():
            if not p.is_open:
                continue
            try:
                if self.tx[mac] and now >= self.tx[mac][0]['next_at']:
                    item = self.tx[mac][0]
                    try:
                        # Transport pacing is explicit. It is not a packet retry.
                        part = item['wire'][item['offset']:item['offset']+32]
                        n = p.write(part)
                        self.record(dict(direction='host_wire_chunk', node_id=mac, nonce=item['nonce'], offset=item['offset'], bytes_hex=part[:n].hex()))
                        item['offset'] += n
                        item['next_at'] = now+.012
                        if item['offset'] == len(item['wire']):
                            self.pending[item['nonce']]['sent_at'] = now
                            self.record(dict(direction='host_tx', evidence_kind='hardware_serial', node_id=mac, command=item['command']))
                            self.tx[mac].pop(0)
                    except serial.SerialException as exc:
                        self.record(dict(direction='host_failure', node_id=mac, nonce=item['nonce'], reason=repr(exc)))
                        self.pending[item['nonce']]['expired'] = True
                        self.tx[mac].pop(0)
                n = p.in_waiting
                if n:
                    data = p.read(min(n, 16384))
                    self.raw[mac].write(data)
                    self.raw[mac].flush()
                    self.buffers[mac].extend(data)
                    while b'\n' in self.buffers[mac]:
                        line, _, tail = self.buffers[mac].partition(b'\n')
                        self.buffers[mac][:] = tail
                        try:
                            event = json.loads(line)
                        except (ValueError, UnicodeError):
                            continue
                        if isinstance(event, dict) and event.get('schema') == 'mid.serial.v1':
                            item = self.record(dict(direction='device_rx', evidence_kind='hardware_serial', port=p.port, event=event))
                            self.events.append(item)
                            nonce = event.get('nonce')
                            if nonce in self.pending and event.get('node_id') == self.pending[nonce]['node']:
                                self.replies[nonce] = event
                                self.reply_sources[nonce] = dict(path=str(self.out/'native.jsonl'), line=item['capture_line'], original_host_ns=item['host_monotonic_ns'])
            except serial.SerialException as exc:
                self.port_errors[mac] = repr(exc)
                self.record(dict(direction='port_error',node_id=mac,port=p.port,error=repr(exc)))
                p.close()
                if not ignore_port_errors:
                    raise
        for nonce, pending in self.pending.items():
            if nonce not in self.replies and pending['sent_at'] is not None and not pending['expired'] and now-pending['sent_at'] > 2:
                pending['expired'] = True
                self.record(dict(direction='command_timeout', nonce=nonce, node_id=pending['node']))

    def wait_command(self, mac, command, seconds=3):
        assert self.submit(mac, command)
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            self.poll()
            if command['nonce'] in self.replies:
                reply = self.replies[command['nonce']]
                if not reply.get('ok'):
                    raise RuntimeError(str(reply))
                return reply
            time.sleep(.002)
        raise RuntimeError('No associated reply: '+command['nonce'])

    def close(self):
        for p in self.ports.values():
            p.close()
        for f in self.raw.values():
            f.close()
        if not self.log.closed:
            self.log.close()
        if self.lease:
            self.lease.__exit__()
            self.lease = None

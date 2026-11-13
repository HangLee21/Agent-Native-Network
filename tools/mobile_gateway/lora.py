"""On-demand LoRa report projection, isolated from the live Wi-Fi State."""
import copy
import datetime
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid

from .server import ROOT

SDK_PYTHON = ROOT/'.local/espnow/E1-015/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe'


class LoRaTopology:
    def __init__(self, output, labels, clock=time.monotonic):
        self.clock, self.labels = clock, dict(labels)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.last_ui, self.last_rx = None, None
        self.reports, self.retired_boots = {}, set()
        self.receiver = dict(state='idle', port=None, gateway_id=None, gateway_boot=None, gateway_swapped=False,
                             error=None, owner='H020-Studio-LoRa', reader_session=None,
                             serial_open=False, pid=None, rejected=0, duplicates=0)
        self.process = None
        self.journal = (Path(output)/'lora-reports.jsonl').open('x', encoding='utf-8')
        self.thread = threading.Thread(target=self.run, daemon=True, name='on-demand-lora-owner')
        self.thread.start()

    def begin_session(self):
        with self.lock:
            self.reports.clear()
            self.retired_boots.clear()
            self.last_rx = None
            self.receiver.update(state='connecting', error=None, gateway_boot=None,
                                 serial_open=False, reader_session=uuid.uuid4().hex, pid=None)

    def ingest(self, event):
        """Called only for an E1-decoded live child event; duplicates never renew age."""
        with self.lock:
            seen = event['gateway_id']
            known = self.receiver.get('gateway_id')
            if known and seen != known:
                # A different gateway now owns this port: drop the old projection instead of
                # failing, so replacing the receiver needs no code change.
                self.reports.clear()
                self.retired_boots.add(('gateway', self.receiver.get('gateway_boot')))
                self.receiver['gateway_swapped'] = True
            self.receiver['gateway_id'] = seen
            report = event['report']
            observer, boot, seq = (report[k] for k in ('observer_id', 'observer_boot', 'report_seq'))
            gateway_boot = event['gateway_boot']
            if self.receiver['gateway_boot'] not in (None, gateway_boot):
                if ('gateway', gateway_boot) in self.retired_boots:
                    return
                self.retired_boots.add(('gateway', self.receiver['gateway_boot']))
                self.reports.clear()
            self.receiver['gateway_boot'] = gateway_boot
            old = self.reports.get(observer)
            if old:
                previous = old['report']
                if boot != previous['observer_boot']:
                    if (observer, boot) in self.retired_boots:
                        return
                    self.retired_boots.add((observer, previous['observer_boot']))
                elif not 0 < ((seq-previous['report_seq']) & 0xffffffff) < 0x80000000:
                    self.receiver['duplicates'] += 1
                    return
            # At most 64 reporter identities per reader session; avoid an unbounded log/projection.
            if observer not in self.reports and len(self.reports) >= 64:
                self.receiver['rejected'] += 1
                return
            now = self.clock()
            row = copy.deepcopy(event)
            row.update(pc_received_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       reader_session=self.receiver['reader_session'], _pc_monotonic=now)
            self.reports[observer] = row
            self.last_rx = now
            self.receiver.update(state='receiving', error=None)
            self.journal.write(json.dumps(row, allow_nan=False)+'\n')
            self.journal.flush()

    def snapshot(self, touch=True):
        with self.lock:
            now = self.clock()
            if touch:
                self.last_ui = now
            receiver = copy.deepcopy(self.receiver)
            age = None if self.last_rx is None else max(0, int((now-self.last_rx)*1000))
            receiver['last_rx_age_ms'] = age
            if receiver['state'] == 'receiving' and age is not None and age > 25000:
                receiver['state'] = 'stale'
            rows = []
            for value in self.reports.values():
                row = copy.deepcopy(value)
                row['pc_receive_age_ms'] = max(0, int((now-row.pop('_pc_monotonic'))*1000))
                rows.append(row)
            return dict(schema='lora.topology.v1', source='lora_received_snapshot',
                        labels=self.labels, receiver=receiver, reports=rows,
                        evidence='state_at_source_snapshot', renew_wifi_mutual=False)

    def active(self):
        return self.last_ui is not None and self.clock()-self.last_ui <= 12

    def consume(self, process):
        try:
            for line in process.stdout:
                item = json.loads(line)
                if item['kind'] == 'report':
                    self.ingest(item['event'])
                else:
                    with self.lock:
                        if item['kind'] == 'rejected':
                            self.receiver['rejected'] += 1
                        else:
                            self.receiver.update({k:v for k,v in item.items() if k != 'kind'})
        except (ValueError, KeyError, OSError) as exc:
            with self.lock:
                self.receiver.update(state='error', error=str(exc))

    def run(self):
        while not self.stop.wait(.2):
            if not self.active():
                continue
            self.begin_session()
            if not SDK_PYTHON.is_file():
                with self.lock:
                    self.receiver.update(state='unavailable', error='缂哄皯宸查厤缃殑涓插彛 Python 鐜')
                self.stop.wait(2)
                continue
            try:
                process = subprocess.Popen([str(SDK_PYTHON), '-X', 'utf8', '-m',
                    'tools.mobile_gateway.lora_reader'], cwd=ROOT, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.process = process
                with self.lock:
                    self.receiver['pid'] = process.pid
                reader = threading.Thread(target=self.consume, args=(process,), daemon=True)
                reader.start()
                while not self.stop.wait(.2) and self.active() and process.poll() is None:
                    pass
                # Pipe EOF releases the serial and hardware lease, including on Studio exit.
                process.stdin.close()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=3)
                reader.join(3)
                process.stdout.close()
                with self.lock:
                    self.receiver.update(serial_open=False, pid=None)
                    if not self.active() or self.stop.is_set():
                        self.receiver.update(state='idle', error=None)
                        self.reports.clear()
                        self.last_rx = None
                    elif self.receiver['state'] in ('connecting', 'receiving'):
                        self.receiver.update(state='error', error='LoRa 璇诲彇杩涚▼宸查€€鍑猴紝姝ｅ湪閲嶈繛')
            except OSError as exc:
                with self.lock:
                    self.receiver.update(state='error', error=str(exc), serial_open=False)
            finally:
                self.process = None
            self.stop.wait(2)

    def close(self):
        self.stop.set()
        self.thread.join(10)
        self.journal.close()


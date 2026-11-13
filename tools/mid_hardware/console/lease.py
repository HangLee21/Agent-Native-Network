"""Windows process lock plus an explicit experiment reservation; no port opens."""
import contextlib
import json
import msvcrt
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT/'.local/mid/H-007'

class Busy(RuntimeError):
    pass

def reserve(owner, reason):
    STATE.mkdir(parents=True, exist_ok=True)
    target = STATE/'reservation.json'
    temp = STATE/'reservation.tmp.json'
    temp.write_text(json.dumps(dict(owner=owner, reason=reason, created_at=time.time())), encoding='utf-8')
    temp.replace(target)

def release_reservation(owner):
    p = STATE/'reservation.json'
    if p.exists() and json.loads(p.read_text())['owner'] == owner:
        p.unlink()

def reservation():
    p = STATE/'reservation.json'
    return json.loads(p.read_text()) if p.exists() else None

class HardwareLease:
    def __init__(self, owner):
        self.owner, self.handle = owner, None

    def __enter__(self):
        STATE.mkdir(parents=True, exist_ok=True)
        reserved = reservation()
        if reserved and reserved['owner'] != self.owner:
            raise Busy('Hardware reserved: '+reserved['owner']+' '+reserved['reason'])
        p = STATE/'serial.lock'
        self.handle = p.open('a+b')
        if p.stat().st_size == 0:
            self.handle.write(b'0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise Busy('Hardware serial process already active') from exc
        (STATE/'owner.json').write_text(json.dumps(dict(owner=self.owner, pid=os.getpid(), started_at=time.time())), encoding='utf-8')
        return self

    def __exit__(self, *_):
        if self.handle:
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            self.handle.close()
            self.handle = None

def status():
    reserved = reservation()
    if reserved:
        return dict(busy=True, reservation=reserved, reason='experiment_reserved')
    try:
        with HardwareLease('status_probe'):
            return dict(busy=False)
    except Busy:
        p = STATE/'owner.json'
        return dict(busy=True, owner=json.loads(p.read_text()) if p.exists() else None, reason='serial_process_active')

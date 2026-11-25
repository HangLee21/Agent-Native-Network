"""Persistent, bounded observation snapshots independent of browser lifetime."""
import json
import sqlite3
import threading
import time
import uuid
import zlib
from pathlib import Path

MAX_PAGE_SIZE = 100


class PaginationRequired(ValueError):
    def __init__(self, total):
        self.total = total
        super().__init__('会话过大，请使用 offset 和 limit 分页读取')


class Replay:
    def __init__(self, path, source, interval=1):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.source = source
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.error = None
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('PRAGMA max_page_count=8192')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, started_ms INTEGER, ended_ms INTEGER, active INTEGER
            );
            CREATE TABLE IF NOT EXISTS frames (session_id TEXT, t_ms INTEGER, topology BLOB);
            CREATE INDEX IF NOT EXISTS frame_session ON frames(session_id,t_ms);
        ''')
        self.db.execute('''UPDATE sessions SET active=0,
            ended_ms=COALESCE((SELECT MAX(t_ms) FROM frames WHERE session_id=sessions.id),started_ms)
            WHERE active=1''')
        self.db.commit()
        self.active = None
        self.thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
        self.thread.start()

    def start(self):
        with self.lock:
            if self.active:
                return self.active
            ident = uuid.uuid4().hex
            self.db.execute('INSERT INTO sessions VALUES(?,?,NULL,1)',
                            (ident, int(time.time() * 1000)))
            self.db.commit()
            self.active = ident
            self.error = None
            return ident

    def stop(self):
        with self.lock:
            ident = self.active
            if ident:
                self.db.execute('UPDATE sessions SET active=0,ended_ms=? WHERE id=?',
                                (int(time.time() * 1000), ident))
                self.db.commit()
                self.active = None
            return ident

    def sample(self):
        with self.lock:
            ident = self.active
        if not ident:
            return
        try:
            value = self.source()
            payload = json.dumps(value, ensure_ascii=False, allow_nan=False,
                                 separators=(',', ':')).encode('utf-8')
        except Exception as exc:
            # Record interruption without inventing reports; keep the session alive.
            value = {'schema': 'lora.topology.v1', 'source': 'unavailable',
                     'source_id': None, 'selection_epoch': None,
                     'receiver': {'state': 'unavailable', 'gateway_observed': False,
                                  'error': str(exc)}, 'reports': [], 'labels': {}}
            payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
        now = int(time.time() * 1000)
        try:
            compressed = zlib.compress(payload, level=6)
            with self.lock:
                if ident != self.active:
                    return
                self.db.execute('INSERT INTO frames VALUES(?,?,?)',
                                (ident, now, sqlite3.Binary(compressed)))
                self.db.commit()
        except (OSError, sqlite3.Error) as exc:
            with self.lock:
                self.db.rollback()
                self.error = str(exc)
                try:
                    self.stop()
                except sqlite3.Error:
                    self.active = None

    def _run(self, interval):
        while not self.stop_event.wait(interval):
            self.sample()

    def sessions(self):
        with self.lock:
            rows = self.db.execute('''SELECT s.id,s.started_ms,s.ended_ms,s.active,COUNT(f.t_ms)
                FROM sessions s LEFT JOIN frames f ON s.id=f.session_id
                GROUP BY s.id ORDER BY s.started_ms DESC''').fetchall()
            return {'sessions': [dict(id=r[0], started_ms=r[1], ended_ms=r[2],
                                      active=bool(r[3]) and r[0] == self.active, count=r[4]) for r in rows],
                    'active_id': self.active, 'error': self.error}

    def session(self, ident, offset=None, limit=None):
        if (offset is None) != (limit is None):
            raise ValueError('offset 和 limit 必须同时指定')
        if offset is not None and (type(offset) is not int or offset < 0 or
                                   type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE):
            raise ValueError('offset 必须非负，limit 必须在 1 至 100 之间')
        with self.lock:
            if not self.db.execute('SELECT 1 FROM sessions WHERE id=?', (ident,)).fetchone():
                return None
            total = self.db.execute('SELECT COUNT(*) FROM frames WHERE session_id=?', (ident,)).fetchone()[0]
            if offset is None:
                if total > MAX_PAGE_SIZE:
                    raise PaginationRequired(total)
                offset, limit = 0, MAX_PAGE_SIZE
            rows = self.db.execute('''SELECT t_ms,topology FROM frames WHERE session_id=?
                ORDER BY rowid LIMIT ? OFFSET ?''', (ident, limit, offset)).fetchall()
        # Older recordings stored JSON as TEXT; retain read compatibility.
        return {'id': ident, 'total': total, 'offset': offset, 'frames': [
            {'t_ms': t, 'topology': json.loads(zlib.decompress(data) if isinstance(data, bytes) else data)}
            for t, data in rows]}

    def close(self):
        self.stop_event.set()
        self.thread.join(3)
        self.stop()
        self.db.close()

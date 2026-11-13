"""Durable request bindings and destination-only PC inbox."""
import json
import secrets
import sqlite3
import threading
import time


class Store:
    def __init__(self, path, request_limit=4096, inbox_limit=1024, pc_id=None):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.request_limit, self.inbox_limit = request_limit, inbox_limit
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, transaction_id INTEGER UNIQUE,
                                                body TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS inbox (cursor INTEGER PRIMARY KEY AUTOINCREMENT,
                                             identity TEXT UNIQUE, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
        ''')
        if pc_id is not None and (type(pc_id) is not int or not 1 <= pc_id <= 0xffffffff):
            raise ValueError('PC ID must be a nonzero uint32')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', ('pc_id', str(pc_id or secrets.randbelow(0xffffffff) + 1)))
            self.db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', ('next_transaction', '1'))
            for key in ('inbox_duplicates', 'inbox_evicted', 'requests_capacity_rejections'):
                self.db.execute('INSERT OR IGNORE INTO counters VALUES (?,0)', (key,))
        self.pc_id = int(self.db.execute("SELECT value FROM metadata WHERE key='pc_id'").fetchone()[0])
        if pc_id is not None and self.pc_id != pc_id:
            self.db.close()
            raise ValueError('state directory belongs to another PC ID')
        self.pc_boot = secrets.randbelow(0xffffffff) + 1

    def get(self, request_id):
        with self.lock:
            row = self.db.execute('SELECT body FROM requests WHERE id=?', (request_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def reserve(self, request_id, request, entry):
        with self.lock, self.db:
            old = self.get(request_id)
            if old:
                if old['request'] != request:
                    raise ValueError('request_id already binds another destination/payload')
                return old, False
            if self.db.execute('SELECT COUNT(*) FROM requests').fetchone()[0] >= self.request_limit:
                raise ValueError('request ledger full; archive this capture and start a new state directory')
            transaction = int(self.db.execute("SELECT value FROM metadata WHERE key='next_transaction'").fetchone()[0])
            if transaction > 0xffffffff:
                raise ValueError('transaction sequence exhausted; use a new state directory')
            record = dict(request_id=request_id, request=request, pc_id=self.pc_id, pc_boot=self.pc_boot,
                          pc_session=self.pc_boot,
                          transaction_id=transaction, entry=entry, state='outcome_unknown',
                          entry_accepted=False, destination_received=False, pc_received=False,
                          delivery_status='destination_unconfirmed', created_at=time.time())
            self.db.execute('INSERT INTO requests VALUES (?,?,?,?)',
                            (request_id, transaction, json.dumps(record), time.time()))
            self.db.execute("UPDATE metadata SET value=? WHERE key='next_transaction'", (str(transaction + 1),))
            return record, True

    def update(self, record):
        with self.lock, self.db:
            self.db.execute('UPDATE requests SET body=? WHERE id=?', (json.dumps(record), record['request_id']))

    def by_transaction(self, transaction):
        with self.lock:
            row = self.db.execute('SELECT body FROM requests WHERE transaction_id=?', (transaction,)).fetchone()
            return json.loads(row[0]) if row else None

    def receive(self, identity, record):
        key = json.dumps(identity, sort_keys=True, separators=(',', ':'))
        with self.lock, self.db:
            cursor = self.db.execute('INSERT OR IGNORE INTO inbox(identity,body) VALUES (?,?)', (key, json.dumps(record)))
            if cursor.rowcount == 0:
                self.db.execute("UPDATE counters SET value=value+1 WHERE key='inbox_duplicates'")
                return False
            excess = self.db.execute('SELECT COUNT(*) FROM inbox').fetchone()[0] - self.inbox_limit
            if excess > 0:
                self.db.execute('DELETE FROM inbox WHERE cursor IN (SELECT cursor FROM inbox ORDER BY cursor LIMIT ?)', (excess,))
                self.db.execute("UPDATE counters SET value=value+? WHERE key='inbox_evicted'", (excess,))
            return True

    def inbox(self, after=0):
        if type(after) is not int or after < 0:
            raise ValueError('nonnegative inbox cursor required')
        with self.lock:
            oldest = self.db.execute('SELECT MIN(cursor) FROM inbox').fetchone()[0]
            rows = self.db.execute('SELECT cursor,body FROM inbox WHERE cursor>? ORDER BY cursor LIMIT 256', (after,)).fetchall()
            return dict(records=[dict(json.loads(body), cursor=cursor) for cursor, body in rows],
                        cursor=rows[-1][0] if rows else after, oldest_cursor=oldest,
                        truncated=bool(oldest and after and after < oldest-1), retained_limit=self.inbox_limit,
                        scope='pc_actual_receive_only')

    def counters(self):
        with self.lock:
            return dict(self.db.execute('SELECT key,value FROM counters').fetchall())

    def close(self):
        self.db.close()

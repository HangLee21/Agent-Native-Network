"""Transactional audit index for archived commands. Never deletes history."""
import json,sqlite3
from pathlib import Path

class Archive:
 def __init__(self,path,eui,required=False):
  if path is not None:Path(path).parent.mkdir(parents=True,exist_ok=True)
  self.db=sqlite3.connect(str(path) if path is not None else ':memory:',timeout=5,check_same_thread=False)
  self.db.execute('PRAGMA journal_mode=DELETE');self.db.execute('PRAGMA synchronous=FULL')
  if required:
   tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
   if not {'metadata','commands'}<=tables or self.db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('required command archive invalid')
  else:
   self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
   self.db.execute('CREATE TABLE IF NOT EXISTS commands (cmd_id TEXT PRIMARY KEY, data TEXT NOT NULL)')
  row=self.db.execute("SELECT value FROM metadata WHERE key='gateway_eui'").fetchone()
  if (required and not row) or (row and row[0]!=eui):raise ValueError('archive gateway EUI mismatch')
  with self.db:self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('gateway_eui',?)",(eui,))
 def get(self,cmd_id):
  row=self.db.execute('SELECT data FROM commands WHERE cmd_id=?',(cmd_id,)).fetchone()
  return json.loads(row[0]) if row else None
 def put(self,cmd):
  prior=self.get(cmd['cmd_id'])
  if prior:
   if prior['request']!=cmd['request']:raise ValueError('conflicting archived command ID')
   if prior.get('receipt') is not None and cmd.get('receipt') is None:cmd=prior
   elif prior.get('receipt') is None and cmd.get('receipt') is None and prior.get('attempts',0)>cmd.get('attempts',0):cmd=prior
  data=json.dumps(cmd,allow_nan=False,separators=(',',':'))
  with self.db:self.db.execute('INSERT INTO commands(cmd_id,data) VALUES(?,?) ON CONFLICT(cmd_id) DO UPDATE SET data=excluded.data',(cmd['cmd_id'],data))
  return cmd
 def close(self):self.db.close()
 def __del__(self):
  try:self.db.close()
  except (AttributeError,sqlite3.Error):pass

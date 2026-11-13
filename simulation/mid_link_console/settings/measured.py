"""Historical measured baseline + editable software assumptions. No hardware access."""
import copy,hashlib,json
from pathlib import Path
from . import routing
SCHEMA='mid.measured.settings.v1'
SettingsError=routing.SettingsError
def get_snapshot():return json.loads(Path(__file__).with_name('measured_snapshot.json').read_text(encoding='utf-8'))
def get_defaults(preset='measured'):
 if preset not in ('measured','normal'):raise SettingsError('preset','请选择“五板实测默认”。')
 s=get_snapshot();d=routing.get_defaults('normal');d.update(schema=SCHEMA,preset='measured',snapshot_id=s['snapshot_id'],hops=None)
 by={(e['src'],e['dst']):e['defaults'] for e in s['edges']}
 for row in d['links']:row.update(copy.deepcopy(by[row['src'],row['dst']]),fail=False)
 return d
def normalize_settings(raw):
 if type(raw) is not dict:raise SettingsError('settings','设置无法读取，请恢复实测默认。')
 if raw.get('schema',SCHEMA)!=SCHEMA:raise SettingsError('schema','请使用实测工作台的配置。')
 baseline=get_defaults();sid=raw.get('snapshot_id',baseline['snapshot_id'])
 if sid!=baseline['snapshot_id']:raise SettingsError('snapshot_id','实测基线版本不同，请恢复实测默认。')
 if raw.get('preset','measured') not in ('measured','normal'):raise SettingsError('preset','请选择“五板实测默认”。')
 allowed=set(baseline)
 if set(raw)-allowed:raise SettingsError('settings','存在未识别设置，请恢复实测默认。')
 d=copy.deepcopy(baseline)
 for k,v in raw.items():
  if k not in ('links','schema','preset','snapshot_id'):d[k]=copy.deepcopy(v)
 if 'duration_s' in raw and 'fault_start_s' not in raw and 'fault_end_s' not in raw:
  times=routing.legacy.normalize_settings({'duration_s':raw['duration_s']});d['fault_start_s'],d['fault_end_s']=times['fault_start_s'],times['fault_end_s']
 rows=raw.get('links',[])
 if type(rows) is not list or len(rows)>20:raise SettingsError('links','连接设置无法读取。')
 indexed={(e['src'],e['dst']):e for e in d['links']};seen=set()
 for row in rows:
  if type(row) is not dict or type(row.get('src')) is not str or type(row.get('dst')) is not str:raise SettingsError('links','请选择连接方向。')
  key=row['src'],row['dst']
  if key not in indexed or key in seen:raise SettingsError('links','连接方向无效或重复。')
  seen.add(key);indexed[key].update(copy.deepcopy(row))
 d.update(schema=routing.SCHEMA,preset='normal');d.pop('snapshot_id')
 result=routing.normalize_settings(d);result.update(schema=SCHEMA,preset='measured',snapshot_id=sid)
 return result
def settings_hash(raw):return hashlib.sha256(json.dumps(normalize_settings(raw),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def compile_scenario(raw):
 d=normalize_settings(raw);snapshot=get_snapshot();old=copy.deepcopy(d);old.update(schema=routing.SCHEMA,preset='normal');old.pop('snapshot_id');s=routing.compile_scenario(old)
 baseline={(e['src'],e['dst']):e['defaults'] for e in snapshot['edges']};start,end=d['fault_start_s'],d['fault_end_s'];s['edges']=[];changed=bool(d['offline_nodes'])
 for row in d['links']:
  b=baseline[row['src'],row['dst']];active=row['connected'];p=0 if row['fail'] else row['success_pct']/100
  e=dict(src=row['src'],dst=row['dst'],pdr=b['success_pct']/100 if active else 0,capacity_payload_bps=b['capacity_kbps']*1000 if active else 0,delay_ms=b['delay_ms'],segments=[])
  if active:
   e['segments']=[dict(start_s=start,end_s=end,pdr_start=p,pdr_end=p,capacity_payload_bps=0 if row['fail'] else row['capacity_kbps']*1000,delay_ms=row['delay_ms'])]
   changed=changed or row['fail'] or any(row[k]!=b[k] for k in ('success_pct','capacity_kbps','delay_ms'))
  s['edges'].append(e)
 s.update(id='measured-'+settings_hash(d)[:16],custom_settings=d,settings_sha256=settings_hash(d),measurement_snapshot=snapshot,
  events=[dict(time_s=start,kind='custom_change_begins'),dict(time_s=end,kind='custom_change_ends')] if changed else [])
 s['assumptions'].append('Baseline service and delivery are historical measured observations; propagation delay and stochastic-link mapping are editable assumptions. Outside intervention restore each direction of the historical baseline.')
 return s
def state_at(scenario,t):return routing.state_at(scenario,t)
def preview(raw,time_s=0):
 s=compile_scenario(raw);d=s['custom_settings'];c=routing.candidate_paths(state_at(s,time_s),d['src'],d['dst'],d['hops'])
 return dict(settings=d,settings_sha256=s['settings_sha256'],time_s=time_s,candidates=c,available=bool(c),routing=s['routing'],message='候选路线仅为快照预览。' if c else '没有满足跳数的路线。',scope='historical_measured_baseline_plus_model_edits_preview_only')
def catalog():
 c=routing.catalog();c.update(schema=SCHEMA,presets=[dict(id='measured',label='五板实测默认')],defaults=get_defaults(),snapshot=get_snapshot(),policy_note='实测快照作历史基线；时延是可编辑模型值，仿真编辑不改变实板状态。')
 return c

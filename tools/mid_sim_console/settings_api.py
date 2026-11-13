"""Explicit schema dispatch; legacy MID and latency-aware routing stay distinct."""
from simulation.mid_link_study.scenarios import custom as mid
from simulation.mid_link_console.settings import routing
SettingsError=mid.SettingsError

def module(raw):
    schema=raw.get('schema') if isinstance(raw,dict) else None
    if schema=='mid.measured.settings.v1':
        from simulation.mid_link_console.settings import measured
        return measured
    if schema==routing.SCHEMA:return routing
    if schema==mid.SCHEMA:return mid
    if schema is not None:raise SettingsError('schema','未知设置版本。')
    if isinstance(raw,dict) and (set(raw)&{'src','dst','hops','both_directions'} or raw.get('preset') in set(routing.PRESETS)-{'normal'}):return routing
    return mid

def normalize_settings(raw):return module(raw).normalize_settings(raw)
def compile_scenario(raw):return module(raw).compile_scenario(raw)
def settings_hash(raw):return module(raw).settings_hash(raw)
def get_defaults(preset=None,mode='routing'):
    lib=mid if mode=='mid' else routing
    return lib.get_defaults(preset) if preset else lib.get_defaults()
def catalog(mode='routing'):
    lib=mid if mode=='mid' else routing
    value=lib.catalog();value['preset_settings']={p['id']:lib.get_defaults(p['id']) for p in value['presets']}
    value['mode']='mid' if mode=='mid' else 'routing'
    if mode!='mid':value['legacy_catalog']=catalog('mid')
    return value

def plan(raw,t=0):
    lib=module(raw)
    if lib is mid:raise SettingsError('schema','候选链预览用于指定跳数模式；原MID可直接开始运行。')
    if type(t) not in (int,float):raise SettingsError('time_s','请选择有效模拟时刻。')
    value=lib.preview(raw,t);value.update(ok=True,evidence_kind='scenario_preview_only',candidate_paths=value['candidates'])
    return value

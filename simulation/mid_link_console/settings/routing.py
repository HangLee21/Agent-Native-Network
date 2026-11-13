"""Explicit-hop, latency-aware simulation settings; legacy MID settings untouched.

candidate_paths operates ONLY on its supplied snapshot. A runtime policy must
pass its delayed observation, not the environment's current/future truth.
"""
import copy
import hashlib
import json
import math

from simulation.mid_link_study.scenarios import custom as legacy

SCHEMA = 'mid.routing.settings.v1'
SettingsError = legacy.SettingsError
NODES = legacy.NODES
PRESETS = {
    'two_hop_failure': '两条2跳路线：一条突然断开',
    'two_hop_delay': '两条2跳路线：一条变慢',
    'three_hop_failure': '两条3跳路线：一条突然断开',
    'three_hop_delay': '两条3跳路线：一条变慢',
    'normal': '两条2跳路线：不添加故障',
}
BASE_KEYS = {'duration_s', 'seed', 'fault_start_s', 'fault_end_s', 'offline_nodes', 'links'}
ROUTE_KEYS = {'src', 'dst', 'hops', 'both_directions'}


def get_defaults(preset='two_hop_failure'):
    if type(preset) is not str or preset not in PRESETS:
        raise SettingsError('preset', '没有这个场景，请重新选择。')
    settings = legacy.get_defaults()
    three = preset.startswith('three_')
    pairs = ['AB','BE','EC','AD','DB','BC'] if three else ['AB','BC','AD','DC']
    enabled = {frozenset(pair) for pair in pairs}
    changed = frozenset('BE' if three else 'BC')
    settings.update(schema=SCHEMA, preset=preset, src='A', dst='C', hops=3 if three else 2,
                    both_directions=False)
    for edge in settings['links']:
        pair = frozenset((edge['src'], edge['dst']))
        edge['connected'] = pair in enabled
        edge['fail'] = preset.endswith('failure') and pair == changed
        if preset.endswith('delay') and pair == changed:
            edge['delay_ms'] = 750.0
    return settings


def normalize_settings(raw):
    if type(raw) is not dict:
        raise SettingsError('settings', '设置无法读取，请点击“恢复默认”后重试。')
    if set(raw) - (BASE_KEYS | ROUTE_KEYS | {'schema','preset'}):
        raise SettingsError('settings', '设置中有无法识别的项目，请恢复默认后重试。')
    if raw.get('schema', SCHEMA) != SCHEMA:
        raise SettingsError('schema', '这不是多跳模拟配置，请选择对应模式或恢复默认。')
    defaults = get_defaults(raw.get('preset', 'two_hop_failure'))
    base = {key: copy.deepcopy(defaults[key]) for key in BASE_KEYS}
    for key in BASE_KEYS - {'links'}:
        if key in raw:
            base[key] = copy.deepcopy(raw[key])
    if 'duration_s' in raw and 'fault_start_s' not in raw and 'fault_end_s' not in raw:
        times = legacy.normalize_settings({'duration_s':raw['duration_s']})
        base['fault_start_s'],base['fault_end_s'] = times['fault_start_s'],times['fault_end_s']
    rows = raw.get('links', [])
    if type(rows) is not list or len(rows) > 20:
        raise SettingsError('links', '链路设置无法读取，请恢复默认后重试。')
    indexed = {(e['src'],e['dst']):e for e in base['links']}
    seen = set()
    for row in rows:
        if type(row) is not dict:
            raise SettingsError('links', '请从图上选择要修改的连接。')
        src,dst = row.get('src'),row.get('dst')
        if type(src) is not str or type(dst) is not str or src not in NODES or dst not in NODES or src == dst:
            raise SettingsError('links', '请在 A 到 E 中选择两个不同节点。')
        key = src,dst
        if key in seen:
            raise SettingsError('links', f'{src} 到 {dst} 的设置重复，请保留一条。')
        seen.add(key)
        indexed[key].update(copy.deepcopy(row))
    normalized = legacy.normalize_settings(dict(base, schema=legacy.SCHEMA, preset='normal'))
    normalized.update(schema=SCHEMA, preset=defaults['preset'])
    for key in ('src','dst'):
        value = raw.get(key,defaults[key])
        if type(value) is not str or value not in NODES:
            raise SettingsError(key, '请选择 A 到 E 中的节点。')
        normalized[key] = value
    if normalized['src'] == normalized['dst']:
        raise SettingsError('dst', '终点要与起点不同。')
    hops = raw.get('hops',defaults['hops'])
    if hops is not None and (type(hops) is not int or not 1 <= hops <= 4):
        raise SettingsError('hops', '请选择“不限跳数”，或 1 到 4 跳。')
    normalized['hops'] = hops
    both = raw.get('both_directions',defaults['both_directions'])
    if type(both) is not bool:
        raise SettingsError('both_directions', '请用开关选择是否同时反向发送。')
    normalized['both_directions'] = both
    return normalized


def settings_hash(settings):
    normalized = normalize_settings(settings)
    return hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def compile_scenario(raw):
    normalized = normalize_settings(raw)
    base = {key: copy.deepcopy(normalized[key]) for key in BASE_KEYS}
    scenario = legacy.compile_scenario(dict(base,schema=legacy.SCHEMA,preset='normal'))
    digest = settings_hash(normalized)
    scenario.update(id='routing-'+digest[:16], settings_sha256=digest,
        custom_settings=normalized, routing=dict(src=normalized['src'],dst=normalized['dst'],
        hops=normalized['hops'],both_directions=normalized['both_directions'],
        policy='latency_aware_simple_path',
        objective='sum(one-way propagation seconds + payload serialization seconds) over available simple paths',
        scope='Software-simulator routing extension, not the original MID SOCP objective.'))
    flows = [dict(src=normalized['src'],dst=normalized['dst'])]
    if normalized['both_directions']:
        flows.append(dict(src=normalized['dst'],dst=normalized['src']))
    scenario['traffic'].update(flows=flows,planned_per_arm=normalized['duration_s']*2*len(flows))
    scenario['description'] = '指定起终点与跳数的时延感知软件模拟'
    scenario['assumptions'].extend([
        'A hop is one directed edge. Exact k hops means k+1 distinct nodes; TTL alone does not impose this.',
        'Positive link success is required for candidate availability; path cost does not imply retries or a QoS guarantee.',
        'Only delayed observed snapshots may enter runtime policy decisions. Candidate preview is not packet delivery.'])
    return scenario


def state_at(scenario,time_s):
    return legacy.state_at(scenario,time_s)


def candidate_paths(snapshot,src,dst,hops=None,payload_bytes=32):
    """Enumerate simple paths in an explicit snapshot. No clocks or scenario access."""
    if src == dst or src not in NODES or dst not in NODES:
        raise SettingsError('dst','请选择两个不同节点。')
    if hops is not None and (type(hops) is not int or not 1 <= hops <= 4):
        raise SettingsError('hops','跳数应为 1 到 4，或不限。')
    if type(payload_bytes) is not int or payload_bytes <= 0:
        raise ValueError('positive payload byte count required')
    active = set(snapshot['active_nodes'])
    if src not in active or dst not in active:
        return []
    graph = {node:[] for node in active}
    edges = {}
    for edge in snapshot['edges']:
        a,b = edge['src'],edge['dst']
        if a in active and b in active and edge['capacity_payload_bps'] > 0 and edge['pdr'] > 0:
            delay = edge.get('propagation_delay_s',edge.get('delay_ms',10)/1000)
            if not math.isfinite(delay) or delay < 0:
                raise ValueError('invalid edge propagation delay')
            graph[a].append(b)
            edges[a,b] = (delay+payload_bytes*8/edge['capacity_payload_bps'],edge['pdr'])
    paths = []
    def visit(path,cost,probability):
        count = len(path)-1
        if path[-1] == dst:
            if hops is None or count == hops:
                paths.append(dict(path=path,hops=count,nodes=len(path),
                    estimated_delay_s=cost,estimated_delay_ms=cost*1000,
                    path_success_probability=probability))
            return
        if count >= (hops if hops is not None else 4):
            return
        for neighbor in sorted(graph[path[-1]]):
            if neighbor not in path:
                delay,pdr = edges[path[-1],neighbor]
                visit(path+[neighbor],cost+delay,probability*pdr)
    visit([src],0.0,1.0)
    return sorted(paths,key=lambda row:(row['estimated_delay_s'],row['path']))


def preview(raw,time_s=0):
    scenario = compile_scenario(raw)
    normalized = scenario['custom_settings']
    state = state_at(scenario,time_s)
    candidates = candidate_paths(state,normalized['src'],normalized['dst'],normalized['hops'])
    return dict(settings=normalized,settings_sha256=scenario['settings_sha256'],time_s=time_s,
        routing=scenario['routing'],candidates=candidates,available=bool(candidates),
        message='可选路线已列出。' if candidates else '没有满足当前跳数的路线，请调整跳数或连接。',
        scope='Assumed-topology preview only. Runtime must use its own delayed observations.')


def catalog():
    result = legacy.catalog()
    result.update(schema=SCHEMA,presets=[dict(id=k,label=v) for k,v in PRESETS.items()],defaults=get_defaults(),
        routing_policy='latency_aware_simple_path',
        policy_label='自动选择时延较低的路线',
        policy_note='这是新增的时延感知策略；原 MID 按服务率和成功率规划。',
        hop_choices=[dict(value=None,label='自动，不限跳数')]+[
            dict(value=k,label=f'{k} 跳（{k+1} 个节点）') for k in range(1,5)])
    result['limits']['hops']=[1,4]
    result['labels'].update(src='起点',dst='终点',hops='经过几跳',both_directions='同时反向发送')
    return result

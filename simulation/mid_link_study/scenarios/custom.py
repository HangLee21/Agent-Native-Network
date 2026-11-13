"""Custom software-simulation settings, defaults and environment compilation.

Never accesses devices, runs solvers, starts services, or writes history.
Link changes apply in the chosen half-open intervention window. Delay is one-way
propagation for both data and control; serialization is additional. UI two-way
edits expand into two explicit directed link rows.
"""
import hashlib
import json
import math

from .scenarios import state_at as base_state_at

SCHEMA = 'mid.console.settings.v1'
NODES = tuple('ABCDE')
PRESETS = {
    'normal': '正常通信',
    'one_link_down': '一条链路断开后恢复',
    'relay_exit': '一块中继离线后返回',
    'partition_restore': '网络断开后恢复',
    'slow_link': '一条链路变慢',
}
BASE_CAPACITY = {frozenset(x): capacity for x, capacity in [
    ('AC', 8.192), ('CD', 8.192), ('DB', 8.192), ('AE', 4.096), ('ED', 4.096)]}


class SettingsError(ValueError):
    def __init__(self, field, message):
        self.field = field
        self.message = message
        super().__init__(message)

    def as_dict(self):
        return {'code': 'invalid_settings', 'field': self.field, 'message': self.message}


def _number(value, field, label, minimum, maximum, integer=False):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise SettingsError(field, f'{label}请填写数字。')
    if integer and int(value) != value:
        raise SettingsError(field, f'{label}请填写整数。')
    if not minimum <= value <= maximum:
        raise SettingsError(field, f'{label}请填写 {minimum} 到 {maximum} 之间的数字。')
    return int(value) if integer else float(value)


def get_defaults(preset='normal'):
    if type(preset) is not str or preset not in PRESETS:
        raise SettingsError('preset', '没有这个场景，请重新选择。')
    settings = dict(schema=SCHEMA, preset=preset, duration_s=60, seed=11,
                    fault_start_s=20, fault_end_s=40, offline_nodes=[], links=[])
    for src in NODES:
        for dst in NODES:
            if src == dst:
                continue
            capacity = BASE_CAPACITY.get(frozenset((src, dst)))
            settings['links'].append(dict(src=src, dst=dst, connected=capacity is not None,
                fail=False, delay_ms=10.0, success_pct=100.0,
                capacity_kbps=capacity if capacity is not None else 8.192))
    if preset == 'relay_exit':
        settings['offline_nodes'] = ['C']
    for edge in settings['links']:
        pair = frozenset((edge['src'], edge['dst']))
        if preset == 'one_link_down' and pair == frozenset('AC'):
            edge['fail'] = True
        if preset == 'partition_restore' and pair == frozenset('DB'):
            edge['fail'] = True
        if preset == 'slow_link' and pair == frozenset('AC'):
            edge['delay_ms'] = 300.0
    return settings


def normalize_settings(raw):
    """Return a complete fresh settings object; sparse link overrides are allowed."""
    if type(raw) is not dict:
        raise SettingsError('settings', '设置无法读取，请点击“恢复默认”后重试。')
    allowed = {'schema', 'preset', 'duration_s', 'seed', 'fault_start_s', 'fault_end_s', 'offline_nodes', 'links'}
    if set(raw) - allowed:
        raise SettingsError('settings', '设置中有无法识别的项目，请点击“恢复默认”后重试。')
    if raw.get('schema', SCHEMA) != SCHEMA:
        raise SettingsError('schema', '设置版本不匹配，请点击“恢复默认”后重试。')
    preset = raw.get('preset', 'normal')
    if type(preset) is not str:
        raise SettingsError('preset', '请从列表中选择场景。')
    settings = get_defaults(preset)
    settings['duration_s'] = _number(raw.get('duration_s', 60), 'duration_s', '模拟时长（秒）', 10, 120, True)
    settings['seed'] = _number(raw.get('seed', 11), 'seed', '随机种子', 1, 2147483647, True)
    end = settings['duration_s']
    start_default, end_default = (20, 40) if end >= 40 else (end / 3, 2 * end / 3)
    settings['fault_start_s'] = _number(raw.get('fault_start_s', start_default), 'fault_start_s', '故障开始时间（秒）', 0, end)
    settings['fault_end_s'] = _number(raw.get('fault_end_s', end_default), 'fault_end_s', '恢复时间（秒）', 0, end)
    if settings['fault_start_s'] >= settings['fault_end_s']:
        raise SettingsError('fault_end_s', '恢复时间要晚于故障开始时间。')
    offline = raw.get('offline_nodes', settings['offline_nodes'])
    if type(offline) is not list or any(type(n) is not str or n not in ('C', 'D', 'E') for n in offline) or len(set(offline)) != len(offline):
        raise SettingsError('offline_nodes', '请选择要临时关闭的中继 C、D 或 E。')
    settings['offline_nodes'] = sorted(offline)
    overrides = raw.get('links', [])
    if type(overrides) is not list or len(overrides) > 20:
        raise SettingsError('links', '链路设置无法读取，请点击“恢复默认”后重试。')
    indexed = {(e['src'], e['dst']): e for e in settings['links']}
    seen = set()
    for row in overrides:
        if type(row) is not dict or set(row) - {'src', 'dst', 'connected', 'fail', 'delay_ms', 'success_pct', 'capacity_kbps'}:
            raise SettingsError('links', '链路设置中有无法识别的项目。')
        a, b = row.get('src'), row.get('dst')
        if type(a) is not str or type(b) is not str or a not in NODES or b not in NODES or a == b:
            raise SettingsError('links', '请在 A 到 E 中选择两个不同节点。')
        key = a, b
        if key in seen:
            raise SettingsError('links', f'{a} 到 {b} 的设置重复了，请保留一条。')
        seen.add(key)
        edge = indexed[key]
        for field in ('connected', 'fail'):
            if field in row:
                if type(row[field]) is not bool:
                    raise SettingsError(field, f'请用开关设置 {a} 到 {b} 是否连接或发生故障。')
                edge[field] = row[field]
        for field, label, lo, hi in [('delay_ms', '链路时延（毫秒）', 0, 2000),
                                     ('success_pct', '链路成功率（%）', 0, 100),
                                     ('capacity_kbps', '链路速率（千比特/秒）', .256, 64)]:
            if field in row:
                edge[field] = _number(row[field], field, label, lo, hi)
        if edge['fail'] and not edge['connected']:
            raise SettingsError('fail', f'{a} 到 {b} 尚未连接，请先连接再设置故障。')
    return settings


def settings_hash(settings):
    canonical = normalize_settings(settings)
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def compile_scenario(raw):
    settings = normalize_settings(raw)
    digest = settings_hash(settings)
    duration = settings['duration_s']
    start, end = settings['fault_start_s'], settings['fault_end_s']
    scenario = dict(schema='mid.link_scenario.v1', version=1, id='custom-' + digest[:16],
        evidence_kind='software_simulation', nodes=list(NODES), duration_s=duration,
        seeds=[settings['seed']], custom_settings=settings, settings_sha256=digest,
        description='用户自定义链路软件模拟',
        units=dict(time='simulated_seconds', capacity_payload_bps='application_payload_bits_per_simulated_second',
                   pdr='conditional_success_probability_per_link_attempt', delay_ms='one_way_propagation_milliseconds'),
        traffic=dict(flows=[dict(src='A', dst='B'), dict(src='B', dst='A')],
            packets_per_direction_per_s=2, payload_bytes=32, first_generation_s=0,
            generation_end_exclusive_s=duration, planned_per_arm=duration * 4),
        positions={'A':[0,0], 'C':[1,1], 'E':[1,-1], 'D':[2,0], 'B':[3,0]},
        assumptions=['Software simulation only; link parameters are user assumptions, not RF measurements.',
            'Link delay is one-way data/control propagation; serialization is additional.',
            'Success, rate and delay overrides apply only during the intervention window; outside it baseline is restored.',
            'Failure intervals are half-open [start,end). Connected=false disables the edge for the whole run.',
            'Each direction is explicit; UI two-way edits must update both directed rows.',
            'Rate is payload-only. Queue, contention, sensing and solving assumptions belong to the engine.'],
        edges=[], node_intervals=[], events=[])
    has_change = bool(settings['offline_nodes']) or any(e['connected'] and (
        e['fail'] or e['delay_ms'] != 10 or e['success_pct'] != 100 or
        e['capacity_kbps'] != BASE_CAPACITY.get(frozenset((e['src'], e['dst'])), 8.192))
        for e in settings['links'])
    if has_change:
        scenario['events'] = [dict(time_s=start, kind='custom_change_begins'), dict(time_s=end, kind='custom_change_ends')]
    for n in settings['offline_nodes']:
        scenario['node_intervals'].append(dict(node=n, start_s=start, end_s=end, online=False))
    for row in settings['links']:
        baseline_capacity = BASE_CAPACITY.get(frozenset((row['src'], row['dst'])), 8.192)
        edge = dict(src=row['src'], dst=row['dst'],
                    capacity_payload_bps=baseline_capacity * 1000 if row['connected'] else 0,
                    pdr=1.0 if row['connected'] else 0.0, delay_ms=10.0, segments=[])
        if row['connected']:
            probability = 0.0 if row['fail'] else row['success_pct'] / 100
            edge['segments'] = [dict(start_s=start, end_s=end, pdr_start=probability,
                pdr_end=probability, capacity_payload_bps=0 if row['fail'] else row['capacity_kbps'] * 1000,
                delay_ms=row['delay_ms'])]
        scenario['edges'].append(edge)
    return scenario


def state_at(scenario, time_s):
    state = base_state_at(scenario, time_s)
    delays = {}
    for e in scenario['edges']:
        delay = e['delay_ms']
        for segment in e['segments']:
            if segment['start_s'] <= time_s < segment['end_s']:
                delay = segment.get('delay_ms', delay)
                break
        delays[e['src'], e['dst']] = delay
    for edge in state['edges']:
        edge['delay_ms'] = delays[edge['src'], edge['dst']]
        edge['propagation_delay_s'] = edge['delay_ms'] / 1000
    return state


def catalog():
    return dict(schema=SCHEMA, presets=[dict(id=k, label=v) for k,v in PRESETS.items()],
        defaults=get_defaults(), nodes=list(NODES),
        limits=dict(duration_s=[10,120],delay_ms=[0,2000],success_pct=[0,100],capacity_kbps=[.256,64]),
        labels=dict(connected='保持连接', fail='在指定时间断开', delay_ms='这段时间的链路时延（毫秒）',
                    success_pct='链路成功率（%）', capacity_kbps='链路速率（千比特/秒）',
                    fault_start_s='故障开始时间（秒）', fault_end_s='恢复时间（秒）'))

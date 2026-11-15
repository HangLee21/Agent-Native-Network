"""Fixed-target hardware bridge. No device imports, arbitrary URL or recovery API."""
import json
import re
import urllib.request
import urllib.error
from simulation.mid_link_console.settings import routing

BASE = 'http://127.0.0.1:8766'
ID = re.compile(r'^[0-9a-f]{24}$')

class BridgeError(Exception):
    def __init__(self, status, value):
        self.status, self.value = status, value

def snapshot():
    from simulation.mid_link_console.settings import measured
    return dict(measured.get_snapshot(),settings=measured.get_defaults())

def hardware_plan(data):
    if 'settings' not in data:
        allowed = {'src','dst','mode','hops','via','count','model_id','node_set','graph_edges','payload_hex','request_id'}
        if set(data)-allowed: raise ValueError('实板规划含不支持的字段。')
        return data
    if set(data)-{'settings','mode','count','payload_hex','request_id','node_set'}: raise ValueError('实板图规划含不支持字段。')
    from settings_api import normalize_settings
    settings = normalize_settings(data['settings'])
    baseline = snapshot()['settings']
    original = {(e['src'],e['dst']):e for e in baseline['links']}
    for e in settings['links']:
        if e['fail'] or any(e[k]!=original[e['src'],e['dst']][k] for k in ['delay_ms','success_pct','capacity_kbps']):
            raise ValueError('时延、成功率、速率修改和时间窗故障仅用于仿真。请恢复实测默认后，仅屏蔽整段连接做实板路由约束。')
    if settings['both_directions']: raise ValueError('实板一次仅支持单向；请选择一个源和目的。')
    mode = data.get('mode','hops' if settings['hops'] is not None else 'mid')
    if mode not in ['hops','mid']: raise ValueError('实板支持MID或指定跳数；时延感知动态改道仅用于仿真。')
    if mode=='mid' and settings['hops'] is not None: raise ValueError('原MID不保证恰好跳数，请选择指定跳数，或将跳数设为不限。')
    if mode=='hops' and settings['hops'] is None: raise ValueError('实板指定跳数需要选择1–4跳。')
    active = [n for n in 'ABCDE' if n not in settings['offline_nodes']]
    if 'node_set' in data:
        if not isinstance(data['node_set'],list) or any(n not in active for n in data['node_set']):raise ValueError('无效实板节点选择。')
        active=data['node_set']
    value = dict(src=settings['src'],dst=settings['dst'],mode=mode,count=data.get('count',1),node_set=active,
        graph_edges=[[e['src'],e['dst']] for e in settings['links'] if e['connected'] and e['src'] in active and e['dst'] in active])
    if mode=='hops': value['hops']=settings['hops']
    for key in ['payload_hex','request_id']:
        if key in data:value[key]=data[key]
    return value

def forward(path, data=None):
    valid = (data is None and (path=='/api/status' or re.fullmatch(r'/api/runs/[0-9a-f]{24}',path))) or (data is not None and (path in ['/api/plan','/api/run'] or re.fullmatch(r'/api/runs/[0-9a-f]{24}/stop',path)))
    if not valid: raise ValueError('不支持的实板接口。')
    if path=='/api/plan': data=hardware_plan(data)
    if path=='/api/run':
        if set(data)!={'plan_id','confirm'} or data['confirm'] is not True or not isinstance(data['plan_id'],str) or not ID.fullmatch(data['plan_id']):
            raise ValueError('实板发送需要有效plan_id和confirm:true；先预览，再显式发送。')
        data={'plan_id':data['plan_id']}
    if path.endswith('/stop') and data: raise ValueError('停止请求必须为{}。')
    # ProxyHandler({}) disables machine proxy configuration even for loopback.
    request=urllib.request.Request(BASE+path, None if data is None else json.dumps(data,allow_nan=False).encode(), headers={'Content-Type':'application/json','Origin':BASE})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=35) as response:
            return response.status,json.load(response)
    except urllib.error.HTTPError as exc:
        raise BridgeError(exc.code,json.load(exc)) from exc
    except (OSError,ValueError) as exc:
        raise BridgeError(503,dict(ok=False,error=dict(code='hardware_service_unavailable',message='8766实板服务不可用，请检查其本机服务。'))) from exc

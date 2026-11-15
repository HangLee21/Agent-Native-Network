"""Read display assignments only; reservation is not device provision or telemetry."""
import json
import re
from pathlib import Path

MAC = re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\Z')


def read_nodes(path, *, optional=False):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        if optional:
            return []
        raise ValueError('fleet 配置文件不存在')
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f'无法读取 {Path(path).name}：{exc}') from exc
    if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1 or not isinstance(data.get('nodes'), list):
        raise ValueError(f'{Path(path).name} 的 schema_version 或 nodes 无效')
    ids, macs, result = set(), set(), []
    for node in data['nodes']:
        if not isinstance(node, dict):
            raise ValueError(f'{Path(path).name} 中节点记录无效')
        ident, mac = node.get('node_id'), node.get('mac')
        if not isinstance(mac, str):
            raise ValueError(f'{Path(path).name} 中 MAC 无效')
        mac = mac.strip().lower()
        if type(ident) is not int or not 1 <= ident <= 0xffffffff or not MAC.fullmatch(mac):
            raise ValueError(f'{Path(path).name} 中节点编号或 MAC 无效')
        if ident in ids or mac in macs:
            raise ValueError(f'{Path(path).name} 中节点编号或 MAC 重复')
        ids.add(ident); macs.add(mac); result.append({'node_id': ident, 'mac': mac})
    return result


def merged_fleet(fleet_path, registry_path):
    fleet = read_nodes(fleet_path)
    registry = read_nodes(registry_path, optional=True)
    by_mac = {n['mac']: n['node_id'] for n in fleet}
    by_id = {n['node_id']: n['mac'] for n in fleet}
    for node in registry:
        mac, ident = node['mac'], node['node_id']
        if (mac in by_mac and by_mac[mac] != ident) or (ident in by_id and by_id[ident] != mac):
            raise ValueError(f'fleet 与 registry 编号或 MAC 冲突：{mac} / {ident}')
        if mac not in by_mac:
            fleet.append(node); by_mac[mac] = ident; by_id[ident] = mac
    return {'schema_version': 1, 'nodes': fleet}

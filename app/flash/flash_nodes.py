"""Offline release checks and fail-closed provisioning orchestration."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
MAC = re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')


@contextmanager
def exclusive_flash():
    import msvcrt
    path=ROOT/'data/flash.lock'; path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        if path.stat().st_size==0: stream.write(b'0');stream.flush()
        stream.seek(0)
        try: msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as exc: raise Blocked('另一个烧录程序正在运行') from exc
        try: yield
        finally:
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)


class Blocked(Exception):
    pass


def operator_hint(message):
    if '没有发现已连接的节点' in message:
        return '请检查设备电源，将 USB 线重新插回原接口，然后再次双击烧录工具。'
    if '节点配置' in message or '编号或 MAC' in message or '正整数编号' in message:
        return '节点信息不完整或重复。请联系交付人员检查节点配置文件，无需修改串口设置。'
    if '依赖缺失' in message:
        return '烧录环境尚未准备好。请联系交付人员安装随交付包提供的运行环境。'
    if '适配器尚未交付' in message:
        return '烧录工具还未准备完成。请联系交付人员获取正式版本。'
    if '镜像' in message or '发布' in message or 'schema' in message or 'source_commit' in message:
        return '烧录包不完整或校验未通过。请联系交付人员重新提供完整的正式烧录包。'
    if '无法读取 JSON' in message:
        return '缺少烧录包或节点配置。请联系交付人员检查交付文件是否完整。'
    return '未能完成准备。请联系交付人员并提供本次检查日志。'


def save_operator_log(message):
    directory=ROOT/'data/logs'
    try:
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/('flash-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json')
        payload={'timestamp':datetime.now(timezone.utc).isoformat(), 'operation':'flash',
                 'result':'not_started', 'requested':'prepare_and_flash', 'completed':[],
                 'error':message, 'device_accessed':False, 'firmware_written':False}
        with path.open('x',encoding='utf-8') as stream:
            json.dump(payload,stream,ensure_ascii=False,indent=2)
        return path
    except OSError:
        return None


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise Blocked(f'无法读取 JSON: {path}: {exc}') from exc


def fleet(path):
    data = read(path)
    if data.get('schema_version') != 1 or not isinstance(data.get('nodes'), list):
        raise Blocked('节点配置 schema_version/nodes 无效')
    result, ids = {}, set()
    for node in data['nodes']:
        ident, mac = node.get('node_id'), node.get('mac')
        if type(ident) is not int or not 1<=ident<=0xffffffff or not isinstance(mac, str) or not MAC.fullmatch(mac):
            raise Blocked('节点必须具有正整数编号和规范小写 MAC')
        if ident in ids or mac in result:
            raise Blocked('节点编号或 MAC 重复')
        ids.add(ident)
        result[mac] = ident
    return result


def release(path):
    path = Path(path).resolve()
    data = read(path)
    f = data.get('firmware') or {}
    if data.get('schema_version') != 1 or data.get('config_schema_version') != 1:
        raise Blocked('发布/配置 schema 不兼容')
    for key in ('release_id', 'source_commit', 'protocol_version'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise Blocked(f'发布信息缺失: {key}')
    if not re.fullmatch(r'[0-9a-f]{40,64}', data['source_commit']):
        raise Blocked('source_commit 必须是完整提交哈希')
    if data.get('status') not in ('candidate', 'validated'):
        raise Blocked('发布状态无效')
    for key in ('path', 'sha256', 'build_id', 'chip', 'partition_layout_id'):
        if not isinstance(f.get(key), str) or not f[key].strip():
            raise Blocked(f'镜像信息缺失: {key}')
    if f['chip'] != 'esp32s3' or f.get('flash_offset') != 0x10000:
        raise Blocked('仅支持已确认 ESP32-S3 的 app-only 0x10000 分区')
    if not re.fullmatch(r'[0-9a-f]{64}', f['sha256']):
        raise Blocked('镜像 SHA256 格式错误')
    image = (path.parent / f['path']).resolve()
    if not image.is_relative_to(path.parent) or not image.is_file():
        raise Blocked('镜像不存在或位于发布目录之外')
    if hashlib.sha256(image.read_bytes()).hexdigest() != f['sha256']:
        raise Blocked('镜像 SHA256 不匹配')
    partition_path,partition_hash=f.get('partition_table_path'),f.get('partition_table_sha256')
    if not isinstance(partition_path,str) or not isinstance(partition_hash,str) or not re.fullmatch(r'[0-9a-f]{64}',partition_hash):
        raise Blocked('发布信息缺少分区表文件或 SHA256')
    partition=(path.parent/partition_path).resolve()
    if not partition.is_relative_to(path.parent) or not partition.is_file(): raise Blocked('分区表文件不存在或不在发布包中')
    raw=partition.read_bytes()
    if len(raw)!=4096 or hashlib.sha256(raw).hexdigest()!=partition_hash: raise Blocked('分区表大小或 SHA256 不匹配')
    return data, image


def main():
    p=argparse.ArgumentParser(description='生产节点烧录：默认只在所有安全合同可验证时工作')
    p.add_argument('--config', type=Path); p.add_argument('--release', type=Path)
    p.add_argument('--dry-run', action='store_true'); p.add_argument('--self-test', action='store_true')
    p.add_argument('--rollback', action='store_true', help='选择 --release 指定的已验证回滚发布，不自动烧录旧镜像')
    args=p.parse_args()
    if args.self_test:
        try:
            config=ROOT/'data/fleet.json'
            if not config.exists(): config=ROOT/'config/fleet.default.json'
            fleet(config); release(ROOT/'firmware/manifest.json')
            import serial, esptool
            if serial.__version__!='3.5' or esptool.__version__!='4.13.0': raise Blocked('运行环境版本不匹配')
            print('离线自检通过；未访问设备。')
            return 0
        except Exception as exc:
            print('离线自检未通过：'+str(exc),file=sys.stderr)
            return 2
    config=args.config or (ROOT/'data/fleet.json')
    if not config.exists() and args.config is None: config=ROOT/'config/fleet.default.json'
    print('正在检查烧录文件和节点信息，请稍候……' if not args.dry_run else '模式: 离线检查', flush=True)
    try:
        nodes=fleet(config)
        configured_release=read(config).get('release_manifest')
        manifest_path=args.release or ((config.resolve().parent/configured_release).resolve() if isinstance(configured_release,str) and configured_release else ROOT/'firmware/manifest.json')
        manifest,image=release(manifest_path)
        if args.rollback and manifest['status'] != 'validated':
            raise Blocked('回滚必须显式指定已验证发布')
        print(f'配置通过：{len(nodes)} 个 MAC；发布 {manifest["release_id"]} ({manifest["status"]})；镜像哈希通过')
        if args.dry_run:
            print('离线检查完成；没有探测设备，尚未验证烧录能力。')
            return 0
        missing=[x for x in ('serial','esptool') if importlib.util.find_spec(x) is None]
        if missing: raise Blocked('Python 依赖缺失: '+', '.join(missing))
        import esptool, serial
        if getattr(esptool,'__version__',None)!='4.13.0' or getattr(serial,'__version__',None)!='3.5':
            raise Blocked('Python 依赖版本不匹配：需要 esptool 4.13.0 和 pyserial 3.5')
        import serial_adapter
        import workflow
        with exclusive_flash():
            config_data=read(config)
            print('正在自动识别连接的设备，请保持 USB 连接……',flush=True)
            directory=ROOT/'data/logs';directory.mkdir(parents=True,exist_ok=True)
            stem='flash-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
            journal=directory/(stem+'.jsonl')
            try:
                with journal.open('x',encoding='utf-8') as stream:
                    def record(event):
                        stream.write(json.dumps(event,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
                    record({'event':'started','release_id':manifest['release_id']})
                    reports=workflow.run_with_retries(serial_adapter,config_data,manifest,image,ROOT/'data/registry.json',directory,
                        lambda number,step: print(f'节点 {number}：{step}',flush=True),record,time.sleep,
                        lambda: print('正在重新连接设备，请保持 USB 连接；如已拔出，请插回原接口。',flush=True))
            except Exception as exc:
                print('操作被中断，设备完成情况未知，请保持连接并联系交付人员。',file=sys.stderr)
                print('进度日志：'+str(journal)+'；原因：'+str(exc),file=sys.stderr)
                return 1
            if not reports:
                raise Blocked('没有发现已连接的节点，请检查 USB 线和电源')
            final_pending=workflow.pending_writes(directory)
            final_rows,success=workflow.summarize_results(reports,final_pending)
            path=directory/(stem+'-result.json')
            with path.open('x',encoding='utf-8') as stream:
                json.dump({'release_id':manifest['release_id'],'boards':final_rows,'history':reports,'unresolved_attempts':list(final_pending),'power_cycle_verified':False},stream,ensure_ascii=False,indent=2)
            for row in final_rows:
                label=str(row.get('node_id','未识别'))
                print(f'节点 {label}：'+('完成，已核对版本和自启设置' if row['result']=='success' else '正在等待恢复，请检查电源并将 USB 线插回原接口，再次双击工具'))
            print('检查日志：'+str(path))
            return 0 if success else 1
    except Blocked as exc:
        if not args.dry_run:
            print('\n本次没有烧录任何设备。',file=sys.stderr)
            print(operator_hint(str(exc)),file=sys.stderr)
            log=save_operator_log(str(exc))
            if log:
                print(f'请将这份检查日志发给交付人员：{log}',file=sys.stderr)
            else:
                print('未能保存检查日志，请将本窗口内容发给交付人员。',file=sys.stderr)
            return 2
        print('未烧录：'+str(exc),file=sys.stderr)
        print('回滚：使用 --rollback --release 指定已验证版本；保留 NVS，禁止全片擦除。',file=sys.stderr)
        return 2


if __name__=='__main__': sys.exit(main())

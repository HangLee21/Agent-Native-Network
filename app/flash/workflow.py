"""Identity-based bounded provisioning; transport injected for offline tests."""
import json
import os
from pathlib import Path
import re
import uuid
import time


class ProvisionError(RuntimeError): pass
MAC=re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')


def summarize_results(reports, pending):
    """Keep independent identities and unknown devices, regardless of USB reuse."""
    latest={}
    for row in reports:
        mac=row.get('mac')
        key=('mac',mac) if isinstance(mac,str) and MAC.fullmatch(mac) else ('unknown',row.get('usb_location'),row.get('port'))
        latest[key]=dict(row)
    for entry in pending.values():
        mac=entry.get('mac')
        if isinstance(mac,str) and MAC.fullmatch(mac):
            key=('mac',mac)
            current=latest.get(key,{'mac':mac,'node_id':entry.get('node_id')})
            current.update(result='unknown',pending_reason='存在未完成的写入记录，等待核验')
            last_error=current.get('error') or entry.get('_last_error')
            if last_error: current['last_error']=last_error
            latest[key]=current
    rows=list(latest.values())
    return rows, bool(rows) and all(row.get('result')=='success' for row in rows)


def load_registry(path, configured):
    result=dict(configured)
    if path.exists():
        try: data=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError,UnicodeError) as exc: raise ProvisionError('本地编号记录无法读取') from exc
        if data.get('schema_version')!=1 or not isinstance(data.get('nodes'),list): raise ProvisionError('本地编号记录无效')
        file_macs,file_ids=set(),set()
        for row in data['nodes']:
            mac,num=row.get('mac'),row.get('node_id')
            if not isinstance(mac,str) or not MAC.fullmatch(mac) or type(num) is not int or not 1<=num<=0xffffffff:
                raise ProvisionError('本地编号记录无效')
            if mac in file_macs or num in file_ids: raise ProvisionError('本地编号记录中 MAC 或编号重复')
            file_macs.add(mac);file_ids.add(num)
            if mac in result and result[mac]!=num: raise ProvisionError('本地编号与交付配置冲突')
            result[mac]=num
    if len(set(result.values())) != len(result): raise ProvisionError('设备编号重复')
    return result


def reserve(path, mapping, mac):
    if mac in mapping: return mapping[mac]
    used=set(mapping.values()); num=next((n for n in range(1,len(used)+2) if n not in used),None)
    if num is None or num>0xffffffff: raise ProvisionError('没有可分配的节点编号')
    mapping[mac]=num
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    payload={'schema_version':1,'nodes':[{'mac':k,'node_id':v} for k,v in sorted(mapping.items())]}
    with temp.open('x',encoding='utf-8') as stream:
        json.dump(payload,stream,ensure_ascii=False,indent=2); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp,path)
    return num


def check_identity(info, mac=None, build=None):
    node=info.get('node_id')
    if not isinstance(node,str) or not MAC.fullmatch(node) or (mac and node!=mac): raise ProvisionError('设备身份异常')
    if info.get('firmware')!='mid-espnow' or info.get('chip')!='esp32s3': raise ProvisionError('设备型号不支持')
    if build and info.get('build_id')!=build: raise ProvisionError('设备版本读回不一致')
    if type(info.get('boot_id')) is not int or not 0<info['boot_id']<=0xffffffff: raise ProvisionError('设备启动标识无效')
    return node


def pending_writes(directory):
    """Fold durable events, preserving the exact attempted image and identity."""
    attempts={}; completed={}; old_unresolved=set(); last_errors={}
    for path in sorted(Path(directory).glob('flash-*.jsonl')):
        old_started=set(); old_success=set(); new_seen=set()
        try:
            with path.open('rb') as stream:
                for line in stream:
                    # A crash may leave an incomplete tail; only complete, fsynced
                    # newline records can advance a write state.
                    if not line.endswith(b'\n'): break
                    event=json.loads(line)
                    if not isinstance(event,dict): raise ValueError('日志记录无效')
                    mac=event.get('mac'); kind=event.get('event'); attempt=event.get('attempt_id')
                    if kind=='write_attempted':
                        if not isinstance(attempt,str) or not isinstance(mac,str) or not MAC.fullmatch(mac): raise ValueError('写入日志缺少身份')
                        if attempt in attempts: raise ValueError('写入事件重复')
                        attempts[attempt]=event;new_seen.add(mac)
                    elif kind=='readback_verified':
                        if not isinstance(attempt,str) or not isinstance(mac,str): raise ValueError('读回日志缺少身份')
                        completed[attempt]=mac
                    elif kind=='progress' and event.get('step')=='写入程序' and isinstance(mac,str): old_started.add(mac)
                    elif kind=='finished' and isinstance(mac,str):
                        if event.get('result')=='success': old_success.add(mac)
                        if event.get('error'): last_errors[mac]=event['error']
        except (OSError,ValueError) as exc:
            raise ProvisionError(f'写入日志损坏，请联系交付人员检查：{path}') from exc
        old_unresolved.update(old_started-old_success-new_seen)
    for attempt,mac in completed.items():
        if attempt not in attempts or attempts[attempt].get('mac')!=mac: raise ProvisionError('写入读回日志不匹配')
    pending={key:value for key,value in attempts.items() if key not in completed}
    for mac in old_unresolved: pending['legacy:'+mac]={'mac':mac}
    for value in pending.values():
        if value['mac'] in last_errors: value['_last_error']=last_errors[value['mac']]
    return pending


def unresolved_writes(directory):
    return {event['mac'] for event in pending_writes(directory).values()}


def finish(board,mac,number,manifest,saved,previous,profile,progress):
    f=manifest['firmware']
    progress('核对版本和编号')
    after=board.info(); check_identity(after,mac,f['build_id'])
    if after.get('node_number_source')=='nvs_error': raise ProvisionError('设备编号存储故障')
    if after.get('node_number')!=number:
        board.command('node_id_set',node_number=number,target_mac=mac,target_boot=after['boot_id'])
    node=board.command('node_id_get')
    if node.get('node_id')!=mac or node.get('node_number')!=number or node.get('node_number_schema')!='node.number.v1':
        raise ProvisionError('设备编号读回失败')
    if not saved:
        progress('设置自动组网')
        board.command('stop')
        board.command('route_config',group=profile['group'],channel=profile['channel'],autostart=True)
    final=board.info(); check_identity(final,mac,f['build_id'])
    if final.get('node_number')!=number or final.get('discovery_fault') is not False or final.get('discovery_saved') is not True or final.get('discovery_autostart') is not True:
        raise ProvisionError('自动组网或编号读回失败')
    if saved and (final.get('group'),final.get('channel'))!=(previous.get('group'),previous.get('channel')):
        raise ProvisionError('原有网络组号或频道发生变化')
    if not saved and (final.get('group'),final.get('channel'))!=(profile['group'],profile['channel']):
        raise ProvisionError('网络组号或频道读回不一致')
    return final


def provision(board, info, number, manifest, image, profile, progress, write_event=lambda *_:None):
    mac=check_identity(info); f=manifest['firmware']
    if info.get('discovery_fault') is not False: raise ProvisionError('设备网络配置状态异常')
    saved=info.get('discovery_saved') is True and info.get('discovery_autostart') is True
    if saved and (type(info.get('group')) is not int or type(info.get('channel')) is not int):
        raise ProvisionError('原有网络组号或频道无法核验')
    if not saved:
        if not isinstance(profile,dict) or type(profile.get('group')) is not int or not 1<=profile['group']<=0xffffffff or type(profile.get('channel')) is not int or not 1<=profile['channel']<=13:
            raise ProvisionError('缺少已确认的网络组号和频道，请联系交付人员配置')
    progress('核验设备和分区')
    board.prepare_rom(mac,f['partition_table_sha256'])
    progress('写入程序')
    write_event('write_attempted')
    board.flash(image)
    write_event('write_completed')
    final=finish(board,mac,number,manifest,saved,info,profile,progress)
    write_event('readback_verified')
    return {'mac':mac,'node_id':number,'build_id':final['build_id'],'boot_id':final['boot_id'],
            'autostart_readback':True,'power_cycle_verified':False}


def execute(transport, config, manifest, image, registry_path, progress, on_record=lambda _:None, blocked_macs=frozenset(), pending=None, skip_macs=frozenset()):
    configured={row['mac']:row['node_id'] for row in config['nodes']}
    mapping=load_registry(registry_path,configured)
    pending=pending or {}; results=[]; seen=set()
    detected=transport.ports()
    on_record({'event':'discovered','ports':list(detected)})
    for index,port in enumerate(detected,1):
        started=time.monotonic()
        board=None; record={'port':port,'result':'failed','flash_attempted':False,'firmware_write_verified':False,'steps':[]}
        try:
            on_record(dict(record,event='starting'))
            progress('未识别',f'[{index}/{len(detected)}] {port} 正在识别，耗时 0.0 秒')
            board=transport.Board(port)
            location=transport.location(port) if hasattr(transport,'location') else None
            record['usb_location']=location
            try:
                info=board.info()
            except Exception:
                if not pending: raise
                if not location or not any(isinstance(v.get('target'),dict) and v['target'].get('usb_location')==location for v in pending.values()):
                    raise ProvisionError('此 USB 位置没有可核验的恢复记录，请重新插回原 USB 接口')
                mac=board.probe_rom();info=None;in_rom=True
                if not isinstance(mac,str) or not MAC.fullmatch(mac): raise ProvisionError('ROM 身份无效')
            else:
                mac=check_identity(info);in_rom=False
            matching={key:entry for key,entry in pending.items() if entry.get('mac')==mac}
            if in_rom and not matching: raise ProvisionError('ROM 设备没有对应身份的恢复记录，未写入')
            if mac in blocked_macs and not matching: raise ProvisionError('该节点上次写入结果未知，暂不能自动恢复')
            if mac in seen: raise ProvisionError('同一设备身份重复出现')
            seen.add(mac)
            if mac in skip_macs:
                record.update(mac=mac,result='skipped');continue
            if info is not None and info.get('discovery_fault') is not False: raise ProvisionError('设备网络配置状态异常')
            record.update(mac=mac,node_id=reserve(registry_path,mapping,mac))
            def step(value):
                record['steps'].append(value)
                on_record(dict(record,event='progress',step=value))
                progress(record['node_id'],f'[{index}/{len(detected)}] {port} 正在执行：{value}，耗时 {time.monotonic()-started:.1f} 秒')
            if hasattr(board,'set_progress'):
                def transfer(done,total,mode,elapsed):
                    pct=100*done//total if total else 0
                    progress(record['node_id'],f'[{index}/{len(detected)}] {port} {mode}：已确认接收 {done}/{total} 字节（{pct}%），耗时 {elapsed:.1f} 秒'+('；正在等待镜像校验和重启' if total and done>=total else ''))
                board.set_progress(transfer)
            attempt_id=uuid.uuid4().hex
            def write_event(value):
                if value=='write_attempted': record['flash_attempted']=True
                if value=='write_completed': record['firmware_write_verified']=True
                on_record(dict(record,event=value,attempt_id=attempt_id))
            if matching:
                targets=[entry.get('target') for entry in matching.values()]
                f=manifest['firmware']
                if any(not isinstance(t,dict) or t.get('image_sha256')!=f['sha256'] or t.get('partition_sha256')!=f['partition_table_sha256'] or t.get('build_id')!=f['build_id'] or t.get('node_id')!=record['node_id'] or type(t.get('saved')) is not bool or (in_rom and t.get('usb_location')!=location) for t in targets):
                    raise ProvisionError('恢复所需的原始镜像或身份记录不完整，请保留设备连接')
                if any(t!=targets[0] for t in targets): raise ProvisionError('待恢复记录的配置互相冲突')
                target=targets[0]; prior={'group':target.get('group'),'channel':target.get('channel')}
                profile={'group':target.get('group'),'channel':target.get('channel')}
                if type(profile['group']) is not int or not 1<=profile['group']<=0xffffffff or type(profile['channel']) is not int or not 1<=profile['channel']<=13:
                    raise ProvisionError('恢复记录缺少已验证网络设置')
                step('检查上次操作')
                if info is not None and info.get('build_id')==f['build_id']:
                    final=finish(board,mac,record['node_id'],manifest,target['saved'],prior,profile,step)
                else:
                    step('恢复程序')
                    if in_rom: board.verify_rom(mac,mac,f['partition_table_sha256'])
                    else: board.prepare_rom(mac,f['partition_table_sha256'])
                    record['target']=target
                    write_event('write_attempted');board.flash(image);write_event('write_completed')
                    final=finish(board,mac,record['node_id'],manifest,target['saved'],prior,profile,step)
                    write_event('readback_verified')
                for old_attempt in matching:
                    on_record(dict(record,event='readback_verified',attempt_id=old_attempt))
                value={'mac':mac,'node_id':record['node_id'],'build_id':final['build_id'],'boot_id':final['boot_id'],'autostart_readback':True,'power_cycle_verified':False,'recovered':True}
            else:
                if in_rom: raise ProvisionError('设备没有可验证的恢复记录，未写入')
                f=manifest['firmware']; saved=info.get('discovery_saved') is True and info.get('discovery_autostart') is True
                profile=config.get('network') or {}
                record['target']={'image_sha256':f['sha256'],'partition_sha256':f['partition_table_sha256'],'build_id':f['build_id'],'node_id':record['node_id'],'saved':saved,'group':info.get('group') if saved else profile.get('group'),'channel':info.get('channel') if saved else profile.get('channel'),'usb_location':location}
                if info.get('build_id')==f['build_id']:
                    if saved and (type(info.get('group')) is not int or type(info.get('channel')) is not int): raise ProvisionError('原有网络配置无法核验')
                    if not saved and (type(profile.get('group')) is not int or not 1<=profile['group']<=0xffffffff or type(profile.get('channel')) is not int or not 1<=profile['channel']<=13): raise ProvisionError('缺少已确认网络配置')
                    final=finish(board,mac,record['node_id'],manifest,saved,info,profile,step)
                    value={'mac':mac,'node_id':record['node_id'],'build_id':final['build_id'],'boot_id':final['boot_id'],'autostart_readback':True,'power_cycle_verified':False,'already_current':True}
                else:
                    value=provision(board,info,record['node_id'],manifest,image,config.get('network'),step,write_event)
            record.update(value,result='success')
        except Exception as exc:
            record['error']=str(exc)
            record['failed_stage']=record['steps'][-1] if record['steps'] else '识别设备'
            record['write_call_entered']=bool(board and getattr(board,'written',False))
            progress(record.get('node_id','未识别'),f'[{index}/{len(detected)}] {port} 已停止，阶段：{record["failed_stage"]}，写入调用：'+('已进入' if record['write_call_entered'] else '未进入')+f'，耗时 {time.monotonic()-started:.1f} 秒：{exc}')
        finally:
            if board:
                record['flash_attempted']=record['flash_attempted'] or getattr(board,'written',False)
                record['firmware_write_verified']=record['firmware_write_verified'] or getattr(board,'write_verified',False)
                try: board.close()
                except Exception as exc:
                    record['result']='failed';record['error']='串口关闭失败: '+str(exc)
            results.append(record)
            on_record(dict(record,event='finished'))
    return results


def run_with_retries(transport,config,manifest,image,registry_path,logdir,progress,on_record,wait,notify):
    """At most three scans; successful MACs are not processed again."""
    reports=[];successful=set()
    for attempt in range(3):
        pending=pending_writes(logdir)
        batch=execute(transport,config,manifest,image,registry_path,progress,on_record,
                      pending=pending,skip_macs=successful)
        reports.extend(row for row in batch if row['result']!='skipped')
        successful.update(row['mac'] for row in batch if row['result']=='success')
        # An observed device failure is actionable, not evidence of a late USB
        # insertion. Do not repeatedly attempt the same protocol/write failure.
        if batch: break
        if attempt<2:
            notify();wait(5)
    return reports

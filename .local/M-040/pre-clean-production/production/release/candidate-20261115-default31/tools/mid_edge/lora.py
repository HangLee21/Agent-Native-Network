"""LoRa reference configuration and the firmware-owned LRN1 decoder."""
import json


def decoder():
    try:
        from . import _lora_decoder
    except ImportError:
        from firmware.mid_baseline.field_agent.lora_ref import decoder as _lora_decoder
    return _lora_decoder


def validate_config(fields):
    if not isinstance(fields,dict) or not fields:
        raise ValueError('at least one LoRa configuration field required')
    ranges={'report_period_ms':(1000,3600000),'jitter_ms':(0,1000),
        'frequency_hz':(410000000,493000000),'sf':(7,12),'coding_rate':(5,8),
        'preamble_symbols':(8,64),'sync_word':(0,255),'tx_power_dbm':(0,0)}
    for key,value in fields.items():
        if key=='role':
            if value not in ('off','rx','tx'):raise ValueError('LoRa role must be off/rx/tx')
        elif key=='start_on_boot':
            if type(value) is not bool:raise ValueError('start_on_boot must be boolean')
        elif key=='bandwidth_hz':
            if type(value) is not int or value not in (125000,250000,500000):raise ValueError('unsupported LoRa bandwidth')
        elif key in ranges:
            low,high=ranges[key]
            if type(value) is not int or not low<=value<=high:raise ValueError('invalid '+key)
        else:raise ValueError('unknown LoRa configuration field: '+key)
    if 'report_period_ms' in fields and 'jitter_ms' in fields and fields['jitter_ms']>fields['report_period_ms']//4:
        raise ValueError('jitter must not exceed one quarter of period')
    return dict(fields)


def readback(requested,status):
    mismatches={};missing=[]
    for key,value in requested.items():
        name='lora_ref_requested_role' if key=='role' else key
        if name not in status:missing.append(key)
        elif status[name]!=value:mismatches[key]=dict(requested=value,read=status[name])
    return dict(matches=not mismatches and not missing,mismatches=mismatches,not_reported=missing,
                basis='explicit_firmware_status_after_persisting_command',reboot_verified=False)


def application_verified(status):
    requested=status.get('requested_generation');applied=status.get('applied_generation')
    role={'off':0,'rx':1,'tx':2}.get(status.get('lora_ref_requested_role'))
    return (type(requested) is int and requested>0 and type(applied) is int and requested==applied
            and type(status.get('lora_ref_worker_state')) is int and status['lora_ref_worker_state']==role)


def decode_event(line,node_id):
    value=json.loads(line)
    if value.get('schema')!='lora.ref.v1':raise ValueError('LoRa reference schema required')
    name=value.get('event')
    identity='gateway_id' if name=='lora_ref_rx' else 'observer_id'
    if value.get(identity)!=node_id:raise ValueError('LoRa serial board identity mismatch')
    if name=='lora_ref_rx':return decoder().decode_serial_line(line)
    if name not in ('lora_ref_tx','lora_ref_config_applied'):raise ValueError('unknown LoRa event')
    return value

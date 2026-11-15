"""field.ip.v2 primitives. Firmware contract lives in field_agent/GATEWAY.md."""
import json
import re

SCHEMA = 'field.ip.v2'
MAX_PAYLOAD = 128
MAX_DATAGRAM = 1024


def uint32(value, name):
    if type(value) is not int or not 1 <= value <= 0xffffffff:
        raise ValueError('nonzero uint32 required: ' + name)
    return value


def mac(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', value):
        raise ValueError('canonical MAC required')
    return value


def payload(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}){0,128}', value):
        raise ValueError('valid 0..128 byte payload_hex required')
    return bytes.fromhex(value)


def encode(operation, **fields):
    data = dict(schema=SCHEMA, op=operation, **fields)
    raw = json.dumps(data, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > MAX_DATAGRAM:
        raise ValueError('field IP datagram exceeds 1024 bytes')
    return raw


def decode(raw):
    if len(raw) > MAX_DATAGRAM:
        raise ValueError('field IP datagram exceeds 1024 bytes')
    value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise ValueError('unexpected IP schema')
    mac(value['entry_id'])
    uint32(value['entry_boot'], 'entry_boot')
    uint32(value['pc_id'], 'pc_id')
    if not isinstance(value.get('event'), str):
        raise ValueError('field event name required')
    session = value.get('pc_session')
    if type(session) is not int or not 0 <= session <= 0xffffffff:
        raise ValueError('uint32 pc_session required')
    return value

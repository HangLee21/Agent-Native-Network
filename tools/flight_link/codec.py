"""E1-032 LRC2/LRA2 v1: fixed length, CRC, target epoch and report anchor."""
import re,struct,zlib
FORMAT=struct.Struct('<4sBBH6sHIIQIIII')
MAC=re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')
OPS={'echo':1,'status':2}

def encode_command(q):
 target=q['target'];op=q['operation'];ident=q['cmd_id'];boot=q['target_boot'];seq=q['report_seq'];ttl=q['ttl_ms'];arg=q.get('value',0)
 if not isinstance(target,str) or not MAC.fullmatch(target) or bytes.fromhex(target.replace(':',''))[0]&1 or not any(bytes.fromhex(target.replace(':',''))):raise ValueError('invalid unicast target')
 if op not in OPS:raise ValueError('LRC2 v1 supports echo/status only')
 if not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f]{16}',ident) or int(ident,16)==0:raise ValueError('cmd_id is a nonzero 16-digit lowercase hex uint64')
 if any(type(x) is not int or not 1<=x<=0xffffffff for x in (boot,seq)) or type(ttl) is not int or not 1000<=ttl<=60000:raise ValueError('invalid boot, report anchor or ttl_ms')
 if type(arg) is not int or not 0<=arg<=0xffffffff or (op=='status' and arg!=0):raise ValueError('echo value is uint32; status value must be zero')
 raw=FORMAT.pack(b'LRC2',1,OPS[op],48,bytes.fromhex(target.replace(':','')),0,boot,seq,int(ident,16),ttl,arg,0,0)
 return raw[:-4]+struct.pack('<I',zlib.crc32(raw[:-4]))

def decode_receipt(raw):
 if not isinstance(raw,bytes) or len(raw)!=48:raise ValueError('invalid LRA2 length')
 magic,version,op,length,mac,flags,boot,seq,ident,status,value,uptime,crc=FORMAT.unpack(raw)
 if magic!=b'LRA2' or version!=1 or op not in (1,2) or length!=48 or flags&~1 or not boot or not seq or not ident or status not in (2,3) or mac[0]&1 or not any(mac) or crc!=zlib.crc32(raw[:-4]):raise ValueError('invalid LRA2 fields or CRC')
 return dict(target=':'.join(f'{b:02x}' for b in mac),target_boot=boot,report_seq=seq,cmd_id=f'{ident:016x}',operation='echo' if op==1 else 'status',executed=status==2,status=status,value=value,uptime_ms=uptime,duplicate=bool(flags&1))

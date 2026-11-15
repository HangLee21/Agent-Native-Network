"""Real local serial adapter; importing this module never enumerates hardware."""
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import time


class AdapterError(RuntimeError):
    pass


class Board:
    def __init__(self, port):
        import serial
        self.port = port
        self.wire = serial.Serial(port=None, baudrate=460800, timeout=.05, write_timeout=2)
        self.wire.dtr = self.wire.rts = False
        self.wire.port = port
        self.wire.open()
        self.buffer = bytearray()
        self.esp = None
        self.written = False
        self.write_verified = False
        self.progress = lambda *_: None

    def set_progress(self, callback):
        self.progress = callback

    @staticmethod
    def check_rom(esp, expected=None):
        actual=':'.join(f'{x:02x}' for x in esp.read_mac())
        sec=esp.get_security_info(); flags=sec['parsed_flags']
        if (expected is not None and actual!=expected) or esp.CHIP_NAME!='ESP32-S3' or flags['SECURE_BOOT_EN'] or flags['SECURE_DOWNLOAD_ENABLE'] or bin(sec['flash_crypt_cnt']).count('1')%2:
            raise AdapterError('ROM 身份或安全状态不匹配')
        return actual

    def close(self):
        try:
            if self.esp is not None and not self.write_verified:
                self.wire.baudrate=460800
                self.esp.hard_reset()
        finally:
            self.wire.close()

    def command(self, name, **fields):
        nonce=secrets.token_hex(12)
        payload=json.dumps(dict(cmd=name, nonce=nonce, **fields), separators=(',', ':')).encode()+b'\n'
        for pos in range(0,len(payload),32):
            part=payload[pos:pos+32]
            if self.wire.write(part)!=len(part): raise AdapterError('串口写入中断，操作状态未知')
            time.sleep(.012)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            self.buffer.extend(self.wire.read(4096))
            if len(self.buffer)>65536: raise AdapterError('串口数据过长')
            while b'\n' in self.buffer:
                raw,_,tail=self.buffer.partition(b'\n'); self.buffer=bytearray(tail)
                try: value=json.loads(raw)
                except (ValueError,UnicodeError): continue
                if isinstance(value,dict) and value.get('schema')=='mid.serial.v1' and value.get('event')=='command_result' and value.get('nonce')==nonce:
                    if value.get('ok') is not True: raise AdapterError('设备拒绝 '+name+': '+str(value.get('error','unknown')))
                    return value
        raise AdapterError('设备未响应 '+name)

    def info(self):
        value=self.command('info')
        if value.get('firmware')!='mid-espnow' or value.get('chip')!='esp32s3':
            raise AdapterError('设备不属于受支持的节点')
        return value

    def prepare_rom(self, mac, partition_sha256):
        import esptool
        self.command('stop')
        status=self.command('stats')
        if status.get('radio') is not False or status.get('queue_depth') != 0:
            raise AdapterError('设备未停止，拒绝写入')
        actual=self.probe_rom()
        self.verify_rom(actual,mac,partition_sha256)

    def probe_rom(self):
        """Identify the ROM without relying on a functional application."""
        import esptool
        self.wire.baudrate=115200
        esp=esptool.detect_chip(self.wire,baud=115200,connect_mode='default_reset',trace_enabled=False,connect_attempts=1)
        try:
            actual=self.check_rom(esp)
            self.esp=esp
            return actual
        except Exception:
            self.wire.baudrate=460800
            esp.hard_reset()
            raise

    def verify_rom(self, actual, expected, partition_sha256):
        import esptool
        esp=self.esp
        if esp is None: raise AdapterError('尚未建立 ROM 身份')
        try:
            if actual != expected: raise AdapterError('ROM 身份不匹配')
            with tempfile.TemporaryDirectory() as directory:
                partition=Path(directory)/'partition.bin'
                esptool.main(['--chip','esp32s3','--port',self.port,'--after','no_reset','read_flash','0x8000','0x1000',str(partition)],esp=esp)
                raw=partition.read_bytes()
                if len(raw)!=4096 or hashlib.sha256(raw).hexdigest()!=partition_sha256:
                    raise AdapterError('设备分区表不匹配，未写入')
            # esptool 4.13 --after no_reset exits its temporary stub to ROM.
            # Re-enter the loader and sync on the existing open port; never reuse
            # the old session after that transition. Recheck the identity.
            self.wire.baudrate=115200
            esp=esptool.detect_chip(self.wire,baud=115200,connect_mode='default_reset',trace_enabled=False,connect_attempts=1)
            self.check_rom(esp,expected)
            self.esp=esp
        except Exception:
            self.wire.baudrate=460800
            esp.hard_reset()
            self.esp=None
            raise

    def flash(self, image):
        import esptool
        if self.esp is None or self.written: raise AdapterError('写入前校验未完成或重复写入')
        image=Path(image).resolve(); original=esptool.write_flash
        started=time.monotonic()
        def guarded(esp,args):
            if self.written or getattr(args,'erase_all',False) or getattr(args,'force',False) or {offset:Path(f.name).resolve() for offset,f in args.addr_filename}!={65536:image}:
                raise AdapterError('仅允许单次应用区写入')
            self.written=True
            originals={k:getattr(esp,k) for k in ('flash_defl_begin','flash_defl_block','flash_begin','flash_block')}
            previous_attempts=esp.WRITE_FLASH_ATTEMPTS
            esp.WRITE_FLASH_ATTEMPTS=1
            state={'total':0,'done':0,'mode':'压缩传输'}
            def begin_compressed(size,compressed,address,*a,**kw):
                value=originals['flash_defl_begin'](size,compressed,address,*a,**kw)
                state.update(total=compressed,done=0,mode='压缩传输');return value
            def begin_plain(size,address,*a,**kw):
                value=originals['flash_begin'](size,address,*a,**kw)
                state.update(total=size,done=0,mode='原始传输');return value
            def done_block(name,block,*a,**kw):
                value=originals[name](block,*a,**kw)
                state['done']=min(state['total'],state['done']+len(block))
                self.progress(state['done'],state['total'],state['mode'],time.monotonic()-started)
                return value
            esp.flash_defl_begin=begin_compressed;esp.flash_begin=begin_plain
            esp.flash_defl_block=lambda block,*a,**kw:done_block('flash_defl_block',block,*a,**kw)
            esp.flash_block=lambda block,*a,**kw:done_block('flash_block',block,*a,**kw)
            try:
                result=original(esp,args)
            finally:
                for name,value in originals.items():setattr(esp,name,value)
                esp.WRITE_FLASH_ATTEMPTS=previous_attempts
            reset=esp.hard_reset
            def reset_at_runtime_baud():
                self.wire.baudrate=460800
                reset()
            esp.hard_reset=reset_at_runtime_baud
            return result
        esptool.write_flash=guarded
        try:
            esptool.main(['--chip','esp32s3','--port',self.port,'--baud','460800','--after','hard_reset','write_flash','0x10000',str(image)],esp=self.esp)
        finally:
            esptool.write_flash=original
        self.write_verified=True
        self.wire.baudrate=460800
        time.sleep(1)
        self.buffer.clear()


def ports():
    from serial.tools.list_ports import comports
    return [p.device for p in comports() if p.vid==0x1a86 and p.pid==0x7523]


def location(port):
    from serial.tools.list_ports import comports
    matches=[p for p in comports() if p.device==port and p.vid==0x1a86 and p.pid==0x7523]
    return matches[0].location if len(matches)==1 else None

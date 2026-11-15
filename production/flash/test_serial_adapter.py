"""Isolated esptool fake; never instantiates or enumerates a real serial port."""
import hashlib
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import serial_adapter

MAC='90:da:72:48:a4:f8'


class Wire:
    baudrate=460800


class ESP:
    CHIP_NAME='ESP32-S3'
    def __init__(self,mac=MAC): self.mac=mac;self.resets=0
    def read_mac(self): return bytes.fromhex(self.mac.replace(':',''))
    def get_security_info(self): return {'parsed_flags':{'SECURE_BOOT_EN':False,'SECURE_DOWNLOAD_ENABLE':False},'flash_crypt_cnt':0}
    def hard_reset(self): self.resets+=1


class Tests(unittest.TestCase):
    def setup_fake(self,raw=b'p'*4096,mac=MAC):
        esp=ESP(mac); fake=types.ModuleType('esptool'); fake.calls=[]
        fake.detect_chip=lambda *a,**k:esp
        def write(_esp,args): fake.calls.append(('write',args.addr_filename));return None
        fake.write_flash=write
        def main(args,esp):
            fake.calls.append(tuple(args))
            if 'read_flash' in args: Path(args[-1]).write_bytes(raw)
            elif 'write_flash' in args:
                with open(args[-1],'rb') as f: fake.write_flash(esp,types.SimpleNamespace(erase_all=False,force=False,addr_filename=[(65536,f)]))
                esp.hard_reset()
        fake.main=main
        board=serial_adapter.Board.__new__(serial_adapter.Board)
        board.port='fake-only';board.wire=Wire();board.esp=None;board.written=False;board.write_verified=False;board.buffer=bytearray()
        board.command=lambda name: {'radio':False,'queue_depth':0} if name=='stats' else {}
        return board,esp,fake
    def test_partition_and_single_app_write(self):
        board,esp,fake=self.setup_fake()
        with TemporaryDirectory() as directory,patch.dict(sys.modules,{'esptool':fake}),patch('serial_adapter.time.sleep'):
            image=Path(directory)/'fake.bin';image.write_bytes(b'mock image')
            board.prepare_rom(MAC,hashlib.sha256(b'p'*4096).hexdigest())
            board.flash(image)
            self.assertTrue(board.written);self.assertEqual(esp.resets,1)
            self.assertTrue(any(x[0]=='write' for x in fake.calls))
            with self.assertRaises(serial_adapter.AdapterError): board.flash(image)
    def test_mismatch_resets_without_write(self):
        for raw,mac in ((b'x'*4096,MAC),(b'p'*4096,'90:da:72:48:a4:e0')):
            board,esp,fake=self.setup_fake(raw,mac)
            with self.subTest(mac=mac,raw=raw[:1]),patch.dict(sys.modules,{'esptool':fake}):
                with self.assertRaises(serial_adapter.AdapterError): board.prepare_rom(MAC,hashlib.sha256(b'p'*4096).hexdigest())
                self.assertFalse(board.written);self.assertEqual(esp.resets,1)


if __name__=='__main__': unittest.main(verbosity=2)

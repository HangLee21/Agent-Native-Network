"""Synthetic serial and real loopback HTTP checks; never opens hardware."""
import json
from pathlib import Path
import queue
import threading
import unittest
from . import Edge,LocalClient,UnsupportedFirmware
from .client import EdgeError

A='90:da:72:48:a4:f8';B='90:da:72:48:a5:cc'


class Serial:
    def __init__(self,supported=True):
        self.rx=queue.Queue();self.buffer=bytearray();self.commands=[];self.closed=False;self.supported=supported
        self.config=dict(role='off',report_period_ms=10000,jitter_ms=250,start_on_boot=False,
            frequency_hz=433000000,sf=7,bandwidth_hz=125000,coding_rate=5,preamble_symbols=8,sync_word=18,tx_power_dbm=0)
    def emit(self,event):self.rx.put((json.dumps(event)+'\n').encode())
    def read(self,size):
        try:return self.rx.get(timeout=.02)
        except queue.Empty:return b''
    def write(self,data):
        self.buffer.extend(data)
        if b'\n' in self.buffer:
            line,_,tail=self.buffer.partition(b'\n');self.buffer[:]=tail;q=json.loads(line);self.commands.append(q)
            fields={};ok=True
            if q['cmd'].startswith('lora_ref_'):
                if not self.supported:ok=False;fields=dict(error='unknown_command')
                else:
                    if q['cmd']=='lora_ref_config':self.config.update({k:v for k,v in q.items() if k in self.config})
                    fields=dict(self.config);fields['lora_ref_requested_role']=fields.pop('role');fields['lora_ref_worker_state']=0
            elif q['cmd']=='info':fields=dict(firmware='mid-espnow',chip='esp32s3')
            self.emit(dict(schema='mid.serial.v1',event='command_result',node_id=A,boot_id=11,nonce=q['nonce'],ok=ok,**fields))
        return len(data)
    def close(self):self.closed=True


class Checks(unittest.TestCase):
    def test_generation_verification_and_missing_readback(self):
        from .lora import application_verified,readback
        status=dict(lora_ref_requested_role='tx',lora_ref_worker_state=2,requested_generation=3,applied_generation=2)
        self.assertFalse(application_verified(status))
        self.assertTrue(application_verified(dict(status,applied_generation=3)))
        self.assertFalse(application_verified(dict(status,applied_generation=3,lora_ref_worker_state=-1)))
        self.assertEqual(readback(dict(start_on_boot=True),status)['not_reported'],['start_on_boot'])

    def test_control_readback_and_wifi_unchanged(self):
        serial=Serial()
        with Edge('synthetic',A,transport=serial) as edge:
            value=edge.lora_config(role='tx',report_period_ms=12000,start_on_boot=True)
            self.assertTrue(value['readback']['matches']);self.assertTrue(value['persistence_acknowledged'])
            self.assertFalse(value['driver_configuration_verified']);self.assertEqual(value['status']['lora_ref_worker_state'],0)
            self.assertEqual([q['cmd'] for q in serial.commands],['lora_ref_status','lora_ref_config','lora_ref_status'])
            self.assertTrue(edge.info()['ok'])
            serial.emit(dict(schema='mid.serial.v1',event='rx_local',node_id=A,boot_id=11,origin=B,origin_boot=22,seq=1,dst=A,payload_hex='00ff'))
            self.assertEqual(edge.recv(1)['payload'],b'\x00\xff')
            for fields in [dict(role='bad'),dict(report_period_ms=True),dict(tx_power_dbm=10),dict(saved=True)]:
                count=len(serial.commands)
                with self.assertRaises(ValueError):edge.lora_config(**fields)
                self.assertEqual(len(serial.commands),count)
        self.assertTrue(serial.closed)

    def test_unsupported_and_no_write(self):
        serial=Serial(False)
        with Edge('synthetic',A,transport=serial) as edge:
            with self.assertRaisesRegex(UnsupportedFirmware,'matching E1-029'):edge.lora_config(role='rx')
            self.assertEqual([q['cmd'] for q in serial.commands],['lora_ref_status'])

    def test_lora_reader_decoder_and_separate_delivery(self):
        sample=json.loads((Path(__file__).resolve().parents[2]/'firmware/mid_baseline/field_agent/lora_ref/samples/serial_rx.json').read_text())
        serial=Serial()
        with Edge('synthetic',A,transport=serial) as edge:
            serial.emit(sample);event=edge.lora_events(wait=1)
            self.assertEqual(len(event['records']),1);self.assertIn('report',event['records'][0])
            self.assertFalse(event['wifi_delivery_evidence'])
            with self.assertRaises(TimeoutError):edge.recv(.03)
            serial.emit(dict(sample,frame_hex='00'))
            serial.emit(dict(sample,gateway_id=B))
            edge.info() # Reader processes preceding malformed frames before this result.
            self.assertEqual(edge.lora_events()['rejected_events'],2)
            self.assertTrue(edge.health()['connected'])

    def test_http_shared_owner_and_unsupported_error(self):
        from http.server import ThreadingHTTPServer
        from types import SimpleNamespace
        from .service_api import Handler
        serial=Serial()
        with Edge('synthetic',A,transport=serial) as edge:
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.app=SimpleNamespace(edge=edge)
            thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                client=LocalClient(server.server_port)
                self.assertEqual(client.lora_status()['lora_ref_requested_role'],'off')
                self.assertTrue(client.lora_config(role='rx',report_period_ms=10000,start_on_boot=True)['readback']['matches'])
                self.assertEqual(client.lora_events()['records'],[])
                serial.supported=False
                with self.assertRaises(UnsupportedFirmware):client.lora_status()
                self.assertTrue(edge.info()['ok'])
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()

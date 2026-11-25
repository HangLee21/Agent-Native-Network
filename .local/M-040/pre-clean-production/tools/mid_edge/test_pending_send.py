"""Synthetic serial acceptance/event correlation; no routes computed by host."""
import json
import queue
import threading
import time
import unittest
from .client import Edge,EdgeError
from .hostcheck import FakeSerial,A,B,C

class PendingSerial(FakeSerial):
    def write(self,data):
        self.buf.extend(data)
        if b'\n' not in self.buf:return len(data)
        line,_,tail=self.buf.partition(b'\n');self.buf[:]=tail;q=json.loads(line)
        self.seq+=q['cmd']=='send'
        if q['cmd']=='send':
            # A previous queued packet is released while this new command replies.
            self.emit(event='tx_queued',origin=A,origin_boot=11,seq=99,dst=q['dst'],next_hop=B)
            self.emit(event='command_result',cmd='send',nonce=q['nonce'],ok=True,origin=A,origin_boot=11,packet_seq=self.seq,dst=q['dst'])
        else:self.emit(event='command_result',cmd=q['cmd'],nonce=q['nonce'],ok=True)
        return len(data)

def eventually(check):
    end=time.monotonic()+2
    while time.monotonic()<end:
        value=check()
        if value:return value
        time.sleep(.005)
    raise AssertionError('reader did not observe injected serial event')

class PendingTests(unittest.TestCase):
    def test_round_scope_and_board_timeout(self):
        transport=PendingSerial(A,{})
        with Edge('synthetic-A',A,transport=transport) as source:
            receipt=source.send(C,b'first');identity={k:receipt[k] for k in ['origin','origin_boot','seq','dst']}
            transport.emit(event='route_waiting',request=7,**identity)
            selected=dict(identity,seq=7);transport.emit(event='route_selected',request=7,path=[A,B,C],**selected)
            transport.emit(event='route_selected',request=8,path=[A,C],**identity)
            transport.emit(event='route_no_route',request=8,reason=3,**identity)
            status=eventually(lambda: (s if (s:=source.packet_status(**identity))['board_selected_paths'] else None))
            self.assertEqual(status['board_selected_paths'][0]['path'],[A,B,C]);self.assertEqual(len(status['board_selected_paths']),1)
            self.assertIsNone(status['board_terminal'])
            transport.emit(event='route_no_route',request=7,reason=3,**identity)
            status=source.wait_packet(**identity,timeout=1)
            self.assertFalse(status['observation_timeout']);self.assertEqual(status['board_terminal'],'route_no_route')
            self.assertEqual(status['delivery_status'],'destination_unconfirmed');self.assertEqual(transport.seq,1)
            receipt=source.send(C,b'stop pending');identity={k:receipt[k] for k in ['origin','origin_boot','seq','dst']}
            transport.emit(event='route_waiting',request=9,**identity)
            transport.emit(event='route_no_route',request=1,reason=6,**identity)  # sr_stop uses a local packet context
            cancelled=source.wait_packet(**identity,timeout=1)
            self.assertEqual(cancelled['board_terminal'],'cancelled_by_stop');self.assertEqual(cancelled['queue_status'],'closed_cancelled')

    def test_identity_pending_transmit_receive_timeout(self):
        bus={};transport=PendingSerial(A,bus);destination=FakeSerial(C,bus)
        with Edge('synthetic-A',A,transport=transport) as source,Edge('synthetic-C',C,transport=destination) as receiver:
            payload=bytes(range(160));receipt=source.send(C,payload)
            self.assertTrue(receipt['accepted']);self.assertEqual(receipt['seq'],1)
            self.assertIsNone(receipt['admission']);self.assertEqual(receipt['admission_state'],'accepted_pending_events')
            identity={k:receipt[k] for k in ['origin','origin_boot','seq','dst']}
            status=source.packet_status(**identity);self.assertEqual(status['queue_status'],'not_observed')
            transport.emit(event='tx_submit',next_hop=B,packet_kind='RREQ',**identity)
            eventually(lambda:any(e.get('packet_kind')=='RREQ' for e in source.events()))
            self.assertEqual(source.packet_status(**identity)['transmission_status'],'not_observed')
            transport.emit(event='tx_queued',next_hop=B,**identity)
            transport.emit(event='tx_submit',next_hop=B,**identity)
            transport.emit(event='tx_link_ok',next_hop=B,**identity)
            status=eventually(lambda: (s if (s:=source.packet_status(**identity))['link_callback']=='success' else None))
            self.assertEqual(status['transmission_status'],'radio_api_accepted');self.assertEqual(status['delivery_status'],'destination_unconfirmed')
            timed=source.wait_packet(**identity,timeout=.02);self.assertTrue(timed['observation_timeout'])
            self.assertEqual(transport.seq,1)  # no automatic business retry
            destination.emit(event='rx_local',payload_hex=payload.hex(),**identity)
            received=receiver.recv(2);self.assertEqual(received['payload'],payload)
            self.assertEqual(receiver.packet_status(**identity)['delivery_status'],'destination_received')
            self.assertEqual(source.packet_status(**identity)['delivery_status'],'destination_unconfirmed')
            with self.assertRaises(ValueError):source.send(C,b'x'*161)

if __name__=='__main__':unittest.main()

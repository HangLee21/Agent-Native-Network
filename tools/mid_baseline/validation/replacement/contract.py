"""Frozen-before-results workload helpers; no device access."""
import struct
def payload(pair_id,direction,slot):
 if not 1<=pair_id<=5 or direction not in [0,1] or not 0<=slot<120:raise ValueError('pair/direction/slot outside fixed design')
 return struct.pack('<4sHBBI',b'RPL1',pair_id,direction,0,slot)+bytes(range(20))
def decode(data):
 if len(data)!=32:raise ValueError('payload must be 32 bytes')
 magic,pair,direction,reserved,slot=struct.unpack('<4sHBBI',data[:12])
 if magic!=b'RPL1' or reserved or data!=payload(pair,direction,slot):raise ValueError('payload does not match design')
 return pair,direction,slot
def slots(pair_id,arm,t0_ns):
 for slot in range(120):
  for direction in [0,1]:yield dict(pair_id=pair_id,arm=arm,direction=direction,slot=slot,planned_ns=t0_ns+slot*500000000,nonce=f'p{pair_id:02d}-{arm}-{direction}-{slot:03d}',payload_hex=payload(pair_id,direction,slot).hex())

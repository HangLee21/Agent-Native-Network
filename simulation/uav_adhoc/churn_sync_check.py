"""Compare periodic/cached sync when an expired ND slot changes identity."""
from pathlib import Path
import sys
from engine import B, Core
core=Core(Path(sys.argv[1]).resolve(),7);l=core.lib;extra=[]
try:
 for mode in ('periodic','cached'):
  receiver=l.host_new(0,7);extra.append(receiver)
  sync=l.host_sync_unlimited if mode=='periodic' else l.host_sync_changed
  for i in range(1,33):
   sender=l.host_new(i,7);extra.append(sender)
   b=B();z=l.host_hello(sender,b);reply=B()
   assert l.host_nd(receiver,i,b,z,100,reply)>0
   challenge=B();z=l.host_hello(receiver,challenge);ack=B()
   az=l.host_nd(sender,0,challenge,z,101,ack);assert az>0
   assert l.host_nd(receiver,i,ack,az,102,B())==0
   sync(receiver,102);assert l.host_peer_state(receiver,i)==1
  sender=l.host_new(33,7);extra.append(sender);b=B();z=l.host_hello(sender,b)
  assert l.host_nd(receiver,33,b,z,12150,B())>0
  sync(receiver,12150)
  assert l.host_peer_state(receiver,1) in (-1,0)
  assert l.host_peer_state(receiver,33)==0
 print('PASS old peer invalidation after ND replacement for periodic/cached sync')
finally:
 for p in extra:l.host_free(p)
 core.close()

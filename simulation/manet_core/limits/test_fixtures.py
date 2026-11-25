"""Deterministic host fixtures; no RF or hardware involved."""
import ctypes as c
import pathlib,sys
lib=c.CDLL(str(pathlib.Path(sys.argv[1]).resolve()))
P=c.c_void_p;U=c.c_uint;B=c.c_ubyte
for name,args,ret in [('host_new',[U,c.c_int],P),('host_free',[P],None),('host_limits',[P,U,U,U],c.c_int),('host_submit',[P,U,U,c.POINTER(B),U,c.c_uint64],c.c_int),('host_service_flags',[P,c.c_uint64],U),('host_next',[P,c.c_uint64,c.POINTER(B),c.POINTER(c.c_int),c.POINTER(c.c_int)],c.c_int),('host_result',[P,c.c_int,c.c_uint64],None),('host_receive',[P,U,c.POINTER(B),U,c.c_uint64],c.c_int),('host_event',[P,c.POINTER(U),c.POINTER(B)],c.c_int)]:
 f=getattr(lib,name);f.argtypes=args;f.restype=ret

def chain(hops, break_at=None):
 nodes=[lib.host_new(i,0) for i in range(hops+1)];payload=(B*4)(1,2,3,4);buf=(B*250)();u=(U*8)();evbuf=(B*250)();events=[];types=[]
 try:
  for node in nodes:assert lib.host_limits(node,32,32,6000)==0
  assert lib.host_submit(nodes[0],hops,1,payload,4,0)==0
  for t in range(0,6000,10):
   for i,n in enumerate(nodes):
    lib.host_service_flags(n,t);d=c.c_int();typ=c.c_int();ln=lib.host_next(n,t,buf,c.byref(d),c.byref(typ))
    if ln:
     types.append(typ.value); targets=[j for j in range(len(nodes)) if abs(i-j)==1] if d.value<0 else [d.value]
     targets=[j for j in targets if abs(i-j)==1 and (break_at is None or {i,j}!=set(break_at))]
     for j in targets:assert lib.host_receive(nodes[j],i,buf,ln,t)>=0
     lib.host_result(n,int(bool(targets)) if d.value>=0 else 1,t)
    while lib.host_event(n,u,evbuf):
     if u[0]==6:events.append((i,u[2],u[3],u[4],bytes(evbuf[:u[7]])))
   if events:break
  return events,types
 finally:
  for n in nodes:lib.host_free(n)
for h in (1,2,4,5,8,16,32):
 e,t=chain(h);assert e==[(h,0,1,1,b'\x01\x02\x03\x04')],(h,e,t);print('chain',h,'PASS')
e,_=chain(3,(1,2));assert not e;print('partition PASS')
n=lib.host_new(1,0);bad=(B*32)();bad[0]=0xa7;bad[1]=9;bad[3]=32;bad[4]=1;bad[5]=0;bad[6]=1
assert lib.host_receive(n,0,bad,32,0)<0;lib.host_free(n);print('unknown version PASS')

def intermediate(policy):
 nodes=[lib.host_new(i,policy) for i in range(4)];edges={(0,1),(1,2),(1,3)};buf=(B*250)();payload=(B*2)(7,8);u=(U*8)();evbuf=(B*250)();found={};relays=0
 try:
  assert lib.host_submit(nodes[0],2,1,payload,2,0)==0
  started=False
  for t in range(0,5000,10):
   if 1 in found and not started:
    assert lib.host_submit(nodes[3],2,9,payload,2,t)==0;started=True
   for i,n in enumerate(nodes):
    lib.host_service_flags(n,t);d=c.c_int();typ=c.c_int();ln=lib.host_next(n,t,buf,c.byref(d),c.byref(typ))
    if ln:
     if started and i==1 and typ.value==1:relays+=1
     targets=[j for j in range(4) if (min(i,j),max(i,j)) in edges] if d.value<0 else [d.value]
     targets=[j for j in targets if (min(i,j),max(i,j)) in edges]
     for j in targets:lib.host_receive(nodes[j],i,buf,ln,t)
     lib.host_result(n,int(bool(targets)) if d.value>=0 else 1,t)
    while lib.host_event(n,u,evbuf):
     if u[0]==6:found[u[4]]=i
   if 9 in found:break
  assert found.get(1)==2,found
  return relays,found.get(9)==2
 finally:
  for n in nodes:lib.host_free(n)
a=intermediate(0);b=intermediate(1);assert a[0]>0 and not a[1] and b==(0,True),(a,b);print('unchanged RREP dropped; intermediate reply delivered',a,b,'PASS')


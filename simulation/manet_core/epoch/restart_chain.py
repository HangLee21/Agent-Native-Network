"""Host-only source restart with changed topology and monotonically newer epoch."""
import ctypes as c,pathlib,sys
lib=c.CDLL(str(pathlib.Path(sys.argv[1]).resolve()));P=c.c_void_p;U=c.c_uint;B=c.c_ubyte
for name,args,ret in [('host_new',[U,c.c_int],P),('host_free',[P],None),('host_set_boot',[P,U],c.c_int),('host_submit',[P,U,U,c.POINTER(B),U,c.c_uint64],c.c_int),('host_service_flags',[P,c.c_uint64],U),('host_next',[P,c.c_uint64,c.POINTER(B),c.POINTER(c.c_int),c.POINTER(c.c_int)],c.c_int),('host_result',[P,c.c_int,c.c_uint64],None),('host_receive',[P,U,c.POINTER(B),U,c.c_uint64],c.c_int),('host_event',[P,c.POINTER(U),c.POINTER(B)],c.c_int)]:
 f=getattr(lib,name);f.argtypes=args;f.restype=ret
nodes=[lib.host_new(i,1) for i in range(4)];buf=(B*250)();evbuf=(B*250)();ev=(U*8)();payload=(B*2)(7,8);delivered=[];after=False
try:
 assert lib.host_submit(nodes[0],2,1,payload,2,0)==0
 for t in range(0,8000,10):
  if delivered and not after:
   lib.host_free(nodes[0]);nodes[0]=lib.host_new(0,1);assert lib.host_set_boot(nodes[0],2)==0
   assert lib.host_submit(nodes[0],2,2,payload,2,t)==0;after=True
  edges={(0,3),(1,3),(1,2)} if after else {(0,1),(1,2)}
  for i,n in enumerate(nodes):
   lib.host_service_flags(n,t);d=c.c_int();typ=c.c_int();ln=lib.host_next(n,t,buf,c.byref(d),c.byref(typ))
   if ln:
    targets=[j for j in range(4) if (min(i,j),max(i,j)) in edges] if d.value<0 else [d.value]
    targets=[j for j in targets if (min(i,j),max(i,j)) in edges]
    for j in targets:lib.host_receive(nodes[j],i,buf,ln,t)
    lib.host_result(n,int(bool(targets)) if d.value>=0 else 1,t)
   while lib.host_event(n,ev,evbuf):
    if ev[0]==6:delivered.append((i,ev[2],ev[3],ev[4],bytes(evbuf[:ev[7]])))
  if len(delivered)==2:break
 assert delivered==[(2,0,1,1,b'\x07\x08'),(2,0,2,2,b'\x07\x08')],delivered
 print('source reboot and new reverse path PASS',delivered)
finally:
 for n in nodes:lib.host_free(n)

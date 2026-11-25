"""Slotted, simplified shared-channel adapter around the actual C ND/SR core."""
import ctypes as C
import hashlib
import json
import math
import random
import time
from collections import deque
from motion import positions, graph, connected_pairs

N = 30
SLOT = 25
B = C.c_ubyte * 250
U = C.c_uint * 8


def deterministic(*args):
    return int.from_bytes(hashlib.blake2s(':'.join(map(str,args)).encode(),digest_size=8).digest(),'little') / 2**64


class Core:
    def __init__(self, dll, policy):
        self.lib = C.CDLL(str(dll))
        signatures = {'host_new':([C.c_uint,C.c_int],C.c_void_p), 'host_free':([C.c_void_p],None),
          'host_tick':([C.c_void_p,C.c_uint64],None), 'host_sync':([C.c_void_p,C.c_uint64],None), 'host_hello':([C.c_void_p,C.POINTER(C.c_ubyte)],C.c_int),
          'host_sync_unlimited':([C.c_void_p,C.c_uint64],None), 'host_peer_access':([C.c_void_p,C.c_int,C.c_uint64],C.c_int),
          'host_sync_changed':([C.c_void_p,C.c_uint64],None),
          'host_service_flags':([C.c_void_p,C.c_uint64],C.c_uint),
          'host_peer_state':([C.c_void_p,C.c_uint],C.c_int),
          'host_state':([C.c_void_p,C.POINTER(C.c_uint)],None),
          'host_nd':([C.c_void_p,C.c_uint,C.POINTER(C.c_ubyte),C.c_uint,C.c_uint64,C.POINTER(C.c_ubyte)],C.c_int),
          'host_submit':([C.c_void_p,C.c_uint,C.c_uint32,C.POINTER(C.c_ubyte),C.c_uint,C.c_uint64],C.c_int),
          'host_next':([C.c_void_p,C.c_uint64,C.POINTER(C.c_ubyte),C.POINTER(C.c_int),C.POINTER(C.c_int)],C.c_int),
          'host_result':([C.c_void_p,C.c_int,C.c_uint64],None), 'host_receive':([C.c_void_p,C.c_uint,C.POINTER(C.c_ubyte),C.c_uint,C.c_uint64],C.c_int),
          'host_event':([C.c_void_p,C.POINTER(C.c_uint),C.POINTER(C.c_ubyte)],C.c_int), 'host_stats':([C.c_void_p,C.POINTER(C.c_uint)],None)}
        for name,(args,ret) in signatures.items():
            fn=getattr(self.lib,name); fn.argtypes=args; fn.restype=ret
        self.nodes=[self.lib.host_new(i,policy) for i in range(N)]
        if not all(self.nodes): raise MemoryError('firmware node allocation')

    def close(self):
        for node in self.nodes: self.lib.host_free(node)


def reachable(edges, src, dst, hop_limit=4):
    frontier={src}; seen={src}
    for _ in range(hop_limit):
        nxt=set()
        for a,b in edges:
            if a in frontier: nxt.add(b)
            if b in frontier: nxt.add(a)
        if dst in nxt: return True
        frontier=nxt-seen;seen |= frontier
    return False


def simulate(dll, mode, speed, seed, policy, seconds, event_file, radius=150, deadline=None):
    core=Core(dll,policy); l=core.lib
    business=[random.Random(seed*101+i+10000) for i in range(N)]
    hello=[random.Random(seed*101+i+20000) for i in range(N)]
    # Backoff draws are indexed by node/slot, so policies cannot consume each other's stream.
    due=[int(r.uniform(2000,3000)) for r in business]
    hdue=[int(r.uniform(0,1000)) for r in hello]
    seq=[0]*N; ndq=[deque() for _ in range(N)]; active=[None]*N
    offered={}; delivered={}; counters={'offered':0,'admitted':0,'submission_rejected':0,'nd_queue_full':0,
        'nd_queue_expired':0,'mac_attempts':0,'mac_collisions':0,'mac_link_failures':0,'control_airtime_ms':0,
        'data_airtime_ms':0,'candidate_count':0,'route_selected':0,'no_route_events':0,'unknown_events':0}
    previous=set(); changes=0; link_open={}; lifetimes=[]; connectivity=[]; prev_tx=set()
    positions_now=None; edges=set(); adj=[set() for _ in range(N)]
    def log(kind,t,src=None,dst=None,sequence=None,reason=None,**extra):
        event_file.write(json.dumps(dict(time_ms=t,event=kind,origin_id=src,origin_boot_id=None if src is None else src+1,
            dst_id=dst,seq=sequence,reason=reason,**extra),separators=(',',':'))+'\n')
    try:
        for t in range(1,seconds*1000+1,SLOT):
            if deadline is not None and (t-1)%2500==0 and time.monotonic()>=deadline:
                raise TimeoutError('batch wall budget during run')
            if (t-1)%250==0:
                positions_now=positions(mode,speed,seed,t/1000)
                edges=graph(positions_now,radius);adj=[set() for _ in range(N)]
                for a,b in edges: adj[a].add(b);adj[b].add(a)
                for edge in edges-previous: link_open[edge]=t
                for edge in previous-edges: lifetimes.append((t-link_open.pop(edge,t))/1000)
                changes+=len(edges^previous) if t>1 else 0;previous=edges
                if (t-1)%1000==0: connectivity.append(connected_pairs(N,edges))
            for i,node in enumerate(core.nodes):
                if (t-1)%250==0:l.host_sync(node,t)
                l.host_tick(node,t)
                if t>=hdue[i]:
                    buf=B(); size=l.host_hello(node,buf);hdue[i]=t+hello[i].randint(2000,3000)
                    if size>0:
                        if len(ndq[i])>=16: counters['nd_queue_full']+=1
                        else: ndq[i].append((bytes(buf[:size]),-1,t))
                if t>=due[i]:
                    dst=business[i].randrange(N-1);dst+=dst>=i;seq[i]+=1; key=(i,i+1,seq[i]);due[i]=t+business[i].randint(2000,3000)
                    can=reachable(edges,i,dst);payload=f'{i}:{seq[i]}:{dst}'.encode(); raw=(C.c_ubyte*len(payload)).from_buffer_copy(payload)
                    counters['offered']+=1; offered[key]={'t':t,'dst':dst,'reachable':can,'payload':payload.hex()}
                    log('offered',t,i,dst,seq[i],geometric_4hop_at_submit=can,payload_hex=payload.hex())
                    if l.host_submit(node,dst,seq[i],raw,len(payload),t)==0: counters['admitted']+=1;offered[key]['admitted']=True;log('admitted',t,i,dst,seq[i])
                    else: counters['submission_rejected']+=1;offered[key]['admitted']=False;log('submission_rejected',t,i,dst,seq[i],reason='firmware_submit_rejected')
                ev=U(); event_payload=B()
                while l.host_event(node,ev,event_payload):
                    typ,reason,src,boot,bseq,dst,request,payload_len=ev
                    if typ==4:counters['candidate_count']+=1
                    if typ==5:counters['route_selected']+=1
                    if typ==7:counters['no_route_events']+=1
                    if typ==9:counters['unknown_events']+=1
                    if typ==6:
                        key=(src,boot,bseq)
                        if key in offered and key not in delivered and i==offered[key]['dst'] and bytes(event_payload[:payload_len]).hex()==offered[key]['payload']:
                            delivered[key]=t;log('destination_received',t,src,i,bseq,bytes_match=True,delay_ms=t-offered[key]['t'])
                    elif typ in (5,7,8,9,10,11): log('sr_'+str(typ),t,src,dst,bseq,reason=str(reason),observer_id=i,request=request)
            for i in range(N):
                while ndq[i] and t-ndq[i][0][2]>=250: ndq[i].popleft();counters['nd_queue_expired']+=1
                if active[i] is None and deterministic(seed,'backoff',i,t)<0.18:
                    if ndq[i]:
                        data,dst,_=ndq[i].popleft();active[i]=dict(data=data,dst=dst,kind='nd',attempt=0,ready=t)
                    else:
                        buf=B();dest=C.c_int();typ=C.c_int();size=l.host_next(core.nodes[i],t,buf,C.byref(dest),C.byref(typ))
                        if size>0:active[i]=dict(data=bytes(buf[:size]),dst=dest.value,kind='sr',type=typ.value,attempt=0,ready=t)
            # Random contention order approximates carrier sensing within a slot;
            # nodes outside one another's sensing range may still collide at a receiver.
            contenders=[i for i,x in enumerate(active) if x and t>=x['ready'] and not (adj[i]&prev_tx)]
            contenders.sort(key=lambda i: deterministic(seed,'priority',i,t))
            tx=[]
            for i in contenders:
                if not any(j in adj[i] for j in tx): tx.append(i)
            for i in tx:
                job=active[i];job['attempt']+=1;counters['mac_attempts']+=1
                counters['data_airtime_ms' if job.get('type')==3 else 'control_airtime_ms']+=SLOT
                targets=adj[i] if job['dst']<0 else {job['dst']}
                successes=[]; collided=False
                for target in targets:
                    if target not in adj[i]:continue
                    if target in tx or any(other!=i and other in adj[target] for other in tx):collided=True;continue
                    # Explicit synthetic directed PHY; no claim of measured PRR.
                    dist=math.dist(positions_now[i],positions_now[target]);prr=max(0.10,min(0.99,1-0.35*(dist/radius)**2))
                    if deterministic(seed,'phy',i,target,t,job['attempt'])<prr:successes.append(target)
                if collided:counters['mac_collisions']+=1
                for target in successes:
                    raw=(C.c_ubyte*len(job['data'])).from_buffer_copy(job['data'])
                    if job['kind']=='nd':
                        reply=B();size=l.host_nd(core.nodes[target],i,raw,len(job['data']),t+SLOT,reply)
                        if size>0:
                            if len(ndq[target])<16:ndq[target].append((bytes(reply[:size]),i,t+SLOT))
                            else:counters['nd_queue_full']+=1
                    else:l.host_receive(core.nodes[target],i,raw,len(job['data']),t+SLOT)
                ok=bool(successes) if job['dst']>=0 else True
                if job['dst']>=0 and not ok and job['attempt']<4:
                    slots=1+int(deterministic(seed,'retry',i,t,job['attempt'])*8)
                    job['ready']=t+slots*SLOT
                    continue
                if job['dst']>=0 and not ok:counters['mac_link_failures']+=1
                if job['kind']=='sr':l.host_result(core.nodes[i],int(ok),t+SLOT)
                active[i]=None
            prev_tx=set(tx)
        stats=[]
        for node in core.nodes:
            x=U();l.host_stats(node,x);stats.append(list(x[:6]))
        latency=sorted(delivered[k]-offered[k]['t'] for k in delivered)
        geo=[k for k,v in offered.items() if v['reachable']]
        counters.update(delivered=len(delivered),offered_geometric_4hop=len(geo),delivered_geometric_4hop=sum(k in delivered for k in geo),
            success_delay_p95_ms=latency[max(0,math.ceil(.95*len(latency))-1)] if latency else None,
            latency_samples=len(latency),edge_changes=changes,completed_link_lifetime_count=len(lifetimes),
            completed_link_lifetime_mean_s=sum(lifetimes)/len(lifetimes) if lifetimes else None,
            right_censored_links=len(link_open),mean_connected_pairs=sum(connectivity)/len(connectivity),node_stats=stats,
            unreceived_at_end=len(offered)-len(delivered))
        return counters
    finally:core.close()

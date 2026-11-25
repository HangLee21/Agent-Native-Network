"""Event-driven host model: microsecond radio and independent 10ms app service.

Synthetic PHY; caller records every model parameter. The C routing core is real.
"""
import ctypes as C
import heapq, json, math, random, time
from collections import deque
from engine import B, U, Core, deterministic, reachable
from motion import positions, graph, scale_initial_separation
from radio_model import duration_us, mark_interference


def simulate_v2(dll, mode, speed, seed, seconds, output, *, density='compact',
                policy=0, rate=1.0, payload_bytes=32, service_ms=10,
                geometry_ms=250, radius=150, phy_rate_mbps=1.0,
                preamble_us=192, slot_us=20, difs_us=50, retry_limit=3,
                peer_eviction_us=0, sync_mode='periodic', deadline=None):
    n=30; core=Core(dll,policy); lib=core.lib
    rng=[random.Random(10909+seed*101+i) for i in range(n)]
    hrng=[random.Random(20909+seed*101+i) for i in range(n)]
    queue=[deque() for _ in range(n)]; active=[None]*n
    offered={}; received={}; tags={}; seq=[0]*n; jobs=[]; order=0
    edges=set(); adj=[set() for _ in range(n)]; points=[]; reach_cache={}
    initial=positions(mode,speed,seed,0) if density=='sparse' else None
    radio=[]; counter=dict(offered=0,admitted=0,rejected=0,nd_queue_full=0,
      nd_queue_expired=0,attempts=0,collision_attempts=0,link_failures=0,
      control_airtime_us=0,data_airtime_us=0,control_sent=0,data_sent=0,
      candidates=0,selected=0,no_route_events=0,unknown_events=0,peer_rejected=0,peer_evicted=0)
    def event(t,kind,*args):
        nonlocal order
        order+=1; heapq.heappush(jobs,(int(t),order,kind,args))
    def log(kind,t,src=None,dst=None,s=None,reason=None,**extra):
        output.write(json.dumps(dict(time_us=t,event=kind,origin_id=src,
          origin_boot_id=None if src is None else src+1,dst_id=dst,seq=s,reason=reason,**extra),separators=(',',':'))+'\n')
    def events(i,t):
        e=U(); b=B()
        while lib.host_event(core.nodes[i],e,b):
            typ,why,src,boot,s,dst,req,ln=e
            if typ==4:counter['candidates']+=1
            if typ==5:counter['selected']+=1
            if typ==7:counter['no_route_events']+=1
            if typ==9:counter['unknown_events']+=1
            key=(src,boot,s)
            if typ in (7,9,10) and key in offered and dst==offered[key]['dst']:
                tags.setdefault(key,set()).add(str(typ)+':'+str(why))
            if typ==6 and key in offered and key not in received and i==offered[key]['dst'] and bytes(b[:ln])==offered[key]['payload']:
                received[key]=t;log('destination_received',t,src,i,s,bytes_match=True,delay_us=t-offered[key]['t'])
            elif typ in (5,7,8,9,10):log('sr_'+str(typ),t,src,dst,s,reason=str(why),observer_id=i,request=req)
    def pump(i,t):
        if active[i] is not None:return
        while queue[i] and t-queue[i][0][2]>1000000:
            queue[i].popleft();counter['nd_queue_expired']+=1
        if queue[i]:
            data,dst,_=queue[i].popleft();job=dict(src=i,data=data,dst=dst,kind='nd',typ=0,attempt=0)
        else:
            buf=B();dst=C.c_int();typ=C.c_int();size=lib.host_next(core.nodes[i],t//1000,buf,C.byref(dst),C.byref(typ))
            if size<=0:return
            job=dict(src=i,data=bytes(buf[:size]),dst=dst.value,kind='sr',typ=typ.value,attempt=0)
        peer_result=lib.host_peer_access(core.nodes[i],job['dst'],t//1000)
        if peer_result<0:
            counter['peer_rejected']+=1
            if job['kind']=='sr' and job['typ']==3 and len(job['data'])>=60:
                wire=job['data'];origin=wire[35]-1;boot=int.from_bytes(wire[12:16],'little');sequence=int.from_bytes(wire[16:20],'little');dst=wire[29]-1
                key=(origin,boot,sequence)
                if key in offered and offered[key]['dst']==dst:
                    tags.setdefault(key,set()).add('peer_capacity_at_'+str(i))
                    log('peer_capacity_rejected',t,origin,dst,sequence,reason='sdk_peer_table_full',observer_id=i)
            if job['kind']=='sr':lib.host_result(core.nodes[i],0,t//1000);events(i,t)
            return
        if peer_result>0:counter['peer_evicted']+=1
        active[i]=job
        slots=int(deterministic(seed,'initial',i,t,job['typ'])*16)
        event(t+difs_us+slots*slot_us+(peer_eviction_us if peer_result>0 else 0),'start',job)
    for i in range(n):
        event(int(hrng[i].uniform(0,1e6)),'hello',i)
        event(int(rng[i].uniform(.5,1.5)/rate*1e6),'offer',i)
    event(0,'geometry');event(0,'service')
    try:
        while jobs:
            t,_,kind,args=heapq.heappop(jobs)
            if t>=seconds*1000000:break
            if deadline is not None and order%4096==0 and time.monotonic()>=deadline:raise TimeoutError('batch wall limit')
            if kind=='geometry':
                points=positions(mode,speed,seed,t/1e6)
                # Scale the initial separation only: scaling full trajectories
                # would also multiply velocities and confound the speed sweep.
                if density=='sparse':points=scale_initial_separation(points,initial,1.6)
                edges=graph(points,radius);adj=[set() for _ in range(n)];reach_cache={}
                for a,b in edges:adj[a].add(b);adj[b].add(a)
                event(t+geometry_ms*1000,'geometry')
            elif kind=='service':
                for i,node in enumerate(core.nodes):
                    if sync_mode=='periodic':lib.host_sync_unlimited(node,t//1000)
                    elif sync_mode=='cached':lib.host_sync_changed(node,t//1000)
                    flags=lib.host_service_flags(node,t//1000)
                    if flags&1:events(i,t)
                    if active[i] is None and (queue[i] or flags&2):pump(i,t)
                event(t+service_ms*1000,'service')
            elif kind=='hello':
                i=args[0]
                if len(queue[i])<16:
                    b=B();size=lib.host_hello(core.nodes[i],b)
                    if size>0:queue[i].append((bytes(b[:size]),-1,t))
                else:counter['nd_queue_full']+=1
                event(t+hrng[i].randint(2000000,3000000),'hello',i)
            elif kind=='nd_expire':
                lib.host_sync_unlimited(core.nodes[args[0]],t//1000)
            elif kind=='offer':
                i=args[0];dst=rng[i].randrange(n-1);dst+=dst>=i;seq[i]+=1;s=seq[i]
                k=(i,i+1,s);can=reach_cache.get((i,dst))
                if can is None:can=reachable(edges,i,dst);reach_cache[(i,dst)]=can
                prefix=f'{i}:{s}:{dst}:'.encode();payload=(prefix+b'x'*payload_bytes)[:payload_bytes]
                offered[k]=dict(t=t,dst=dst,payload=payload,reachable=can)
                counter['offered']+=1;log('offered',t,i,dst,s,geometric_4hop_at_submit=can,payload_hex=payload.hex())
                raw=(C.c_ubyte*len(payload)).from_buffer_copy(payload)
                if lib.host_submit(core.nodes[i],dst,s,raw,len(payload),t//1000)==0:
                    offered[k]['admitted']=True;counter['admitted']+=1;log('admitted',t,i,dst,s)
                else:offered[k]['admitted']=False;counter['rejected']+=1;tags[k]={'submit_rejected'};log('submission_rejected',t,i,dst,s,reason='firmware_submit_rejected')
                events(i,t);event(t+int(rng[i].uniform(.8,1.2)/rate*1e6),'offer',i)
            elif kind=='start':
                job=args[0];i=job['src']
                sensed=[x for x in radio if x['end']>t and x['src'] in adj[i]]
                if sensed:
                    backoff=int(deterministic(seed,'sense',i,t,job['attempt'])*16)*slot_us
                    event(max(x['end'] for x in sensed)+difs_us+backoff,'start',job);continue
                targets=set(adj[i]) if job['dst']<0 else ({job['dst']} & adj[i])
                # 802.11 1 Mb/s long preamble plus explicit conservative overhead;
                # unicast includes ACK wait; this is a configurable approximation.
                frame_us,ack_us=duration_us(len(job['data']),phy_rate_mbps,preamble_us,job['dst']>=0)
                x=dict(src=i,start=t,end=t+frame_us+ack_us,job=job,targets=targets,collided=set())
                mark_interference(x,radio,adj)
                radio.append(x);job['attempt']+=1;counter['attempts']+=1
                counter['data_airtime_us' if job['typ']==3 else 'control_airtime_us']+=frame_us+ack_us
                event(x['end'],'finish',x)
            elif kind=='finish':
                x=args[0];radio.remove(x);job=x['job'];i=job['src'];success=[]
                if x['collided']:counter['collision_attempts']+=1
                for target in x['targets']-x['collided']:
                    dist=math.dist(points[i],points[target]);prr=max(.10,min(.99,1-.35*(dist/radius)**2))
                    if deterministic(seed,'phy2',i,target,t,job['attempt'])<prr:success.append(target)
                for target in success:
                    raw=(C.c_ubyte*len(job['data'])).from_buffer_copy(job['data'])
                    if job['kind']=='nd':
                        reply=B();size=lib.host_nd(core.nodes[target],i,raw,len(job['data']),t//1000,reply)
                        if sync_mode=='event' and size>=0:
                            lib.host_sync_unlimited(core.nodes[target],t//1000)
                            for interval in (9000,12000):
                                when=((t//1000+interval+service_ms-1)//service_ms)*service_ms*1000
                                event(when,'nd_expire',target)
                        if size>0:
                            if len(queue[target])<16:queue[target].append((bytes(reply[:size]),i,t))
                            else:counter['nd_queue_full']+=1
                    else:lib.host_receive(core.nodes[target],i,raw,len(job['data']),t//1000)
                    events(target,t)
                ok=bool(success) if job['dst']>=0 else True
                if not ok and job['dst']>=0 and job['attempt']<=retry_limit:
                    window=min(128,16*(2**job['attempt']));slots=int(deterministic(seed,'retry2',i,t,job['attempt'])*window)
                    event(t+difs_us+slots*slot_us,'start',job);continue
                if not ok:counter['link_failures']+=1
                counter['data_sent' if job['typ']==3 else 'control_sent']+=1
                if job['kind']=='sr':lib.host_result(core.nodes[i],int(ok),t//1000);events(i,t)
                active[i]=None
            else:raise RuntimeError(kind)
        for i in range(n):events(i,seconds*1000000)
        core_stats=[]
        lib.host_extended.argtypes=[C.c_void_p,C.POINTER(C.c_uint)]
        lib.host_extended.restype=None
        lib.host_extended2.argtypes=[C.c_void_p,C.POINTER(C.c_uint)]
        lib.host_extended2.restype=None
        extended=[]
        for node in core.nodes:
            z=U();lib.host_extended(node,z);extended.append(dict(zip(('tx_queue_overflow','seen_cache_overflow','rreq_received','rreq_duplicates','rreq_forward','rrep_destination','rrep_intermediate','rerr_issued'),list(z))));w=U();lib.host_extended2(node,w);extended[-1]['rreq_rate_suppressed']=w[0]
        for node in core.nodes:
            stats=U();lib.host_stats(node,stats)
            core_stats.append(dict(sr_overflows=stats[0],rreq_denied=stats[1],sr_rejected=stats[2],
              event_overflows=stats[3],nd_table_full=stats[4],pending_high=stats[6],out_high=stats[7]))
        delays=sorted(received[k]-offered[k]['t'] for k in received)
        def pct(p):return delays[math.ceil(p*len(delays))-1]/1000 if delays else None
        end_us=seconds*1000000
        def deadline_status(k,v,limit):
            if not v['admitted']:return 'submission_rejected'
            if k in received and received[k]-v['t']<=limit:return 'received_on_time'
            if v['t']+limit>end_us:return 'right_censored'
            return 'no_endpoint_receipt_by_deadline'
        for k,v in offered.items():
            log('deadline_outcome',end_us,k[0],v['dst'],k[2],
                reason='run_end_accounting',submitted_us=v['t'],
                received_us=received.get(k),status_500ms=deadline_status(k,v,500000),
                status_1s=deadline_status(k,v,1000000),status_2s=deadline_status(k,v,2000000),
                observed_sr_tags=sorted(tags.get(k,set())))
        counter.update(delivered=len(received),delivery_p95_ms=pct(.95),delivery_p99_ms=pct(.99),
          extended_by_node=extended,core_stats_by_node=core_stats,core_sr_overflows=sum(x['sr_overflows'] for x in core_stats),
          core_rreq_denied=sum(x['rreq_denied'] for x in core_stats),core_sr_rejected=sum(x['sr_rejected'] for x in core_stats),
          core_event_overflows=sum(x['event_overflows'] for x in core_stats),core_nd_table_full=sum(x['nd_table_full'] for x in core_stats),
          event_recording_complete=not any(x['event_overflows'] for x in core_stats),
          within_500ms=sum(received[k]-offered[k]['t']<=500000 for k in received),
          within_1s=sum(received[k]-offered[k]['t']<=1000000 for k in received),
          within_2s=sum(received[k]-offered[k]['t']<=2000000 for k in received),
          eligible_500ms=sum(v['t']+500000<=end_us for v in offered.values()),
          eligible_1s=sum(v['t']+1000000<=seconds*1000000 for v in offered.values()),
          eligible_2s=sum(v['t']+2000000<=end_us for v in offered.values()),
          eligible_within_1s=sum(k in received and received[k]-v['t']<=1000000 for k,v in offered.items() if v['t']+1000000<=end_us),
          geom4_at_submit=sum(v['reachable'] for v in offered.values()),
          unreceived_at_end=len(offered)-len(received))
        return counter
    finally:core.close()

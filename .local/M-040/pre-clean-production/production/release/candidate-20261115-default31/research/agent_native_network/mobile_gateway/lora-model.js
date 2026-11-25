'use strict';
// LoRa transports source snapshots. It never establishes current Wi-Fi freshness.
const MobileLoRaModel=(()=>{
  const clean=x=>String(x||'').trim().toLowerCase(),valid=x=>/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(clean(x));
  // The Ethernet gateway is identified by an EUI-64 (16 hex digits, no separators), which is
  // not a MAC, so label lookup needs to accept it as well.
  const validLabelId=x=>valid(x)||/^[0-9a-f]{16}$/.test(clean(x));
  const number=x=>Number.isFinite(x)?x:null;
  function snapshot(data,elapsed=0){
    const labels=new Map(),nodes=new Map(),edges=[],reports=[];
    for(const [id,name]of Object.entries(data?.labels||{}))if(validLabelId(id)&&typeof name==='string')labels.set(clean(id),name);
    const member=(id,name)=>{if(!valid(id))return;id=clean(id);if(typeof name==='string'&&name.trim())labels.set(id,name.trim());if(!nodes.has(id))nodes.set(id,{id});};
    // The receiver itself is a vertex: every reporting node reaches it over a LoRa uplink,
    // which is a different kind of edge from the ESP-NOW rows the report carries.
    const gateway=clean(data?.receiver?.gateway_id);
    const hasGateway=validLabelId(gateway);
    if(hasGateway){
      if(!nodes.has(gateway))nodes.set(gateway,{id:gateway});
      nodes.get(gateway).gateway=true;
    }
    for(const item of data?.reports||[]){
      const r=item.report;if(!r||r.frame_schema!=='LRN1'||!valid(r.observer_id))continue;
      const id=clean(r.observer_id),receivedAge=number(item.pc_receive_age_ms),entry={...item,report:r,id,age:receivedAge===null?null:Math.max(0,receivedAge+elapsed)};
      reports.push(entry);member(id,item.label);nodes.get(id).report=entry;
      for(const row of r.neighbors||[]){
        if(!valid(row.peer_id)||clean(row.peer_id)===id)continue;
        const peer=clean(row.peer_id);member(peer,row.label);
        edges.push({from:peer,to:id,state:row.state,age:number(row.seen_age_ms),ageLowerBound:null,ageUpperBound:null,rssi:number(row.rssi_dbm),rssiAge:number(row.rf_age_ms),sampleFreshness:'unknown',sampleStale:false,observerStale:false,hasObservation:true,mutual:false,rf_source:'LoRa回传的 ESP-NOW 采样',raw:row,loraReport:entry});
      }
      if(hasGateway&&gateway!==id){
        const link=entry.lora||{};
        edges.push({from:id,to:gateway,state:'uplink',kind:'lora_uplink',hasObservation:true,mutual:false,
          age:entry.age,ageLowerBound:null,ageUpperBound:null,rssi:number(link.rssi_dbm),rssiAge:null,
          snr:number(link.snr_db),channel:link.channel??null,frequency_hz:link.frequency_hz??null,
          sampleFreshness:'unknown',sampleStale:false,observerStale:false,
          rf_source:'网关直接接收',raw:{freq:link.frequency_hz,chan:link.channel,rssi:link.rssi_dbm,lsnr:link.snr_db},
          loraReport:entry});
      }
    }
    // A member is "reported" when its own LoRa report arrived, "seen" when only other
    // observers list it as still valid, "lost" when every row about it is lost, and
    // "gateway" for the receiver itself.
    const live=new Set(),gone=new Set();
    for(const e of edges){if(e.kind==='lora_uplink')continue;(e.state==='lost'?gone:live).add(e.from);(e.state==='lost'?gone:live).add(e.to);}
    for(const n of nodes.values()){const limit=data?.receiver?.recent_threshold_ms,age=n.report?.age,observed=data?.receiver?.gateway_observed;n.status=n.gateway?'gateway':n.report?(observed===false||Number.isFinite(limit)&&Number.isFinite(age)&&age>limit?'stale_report':observed===true&&Number.isFinite(limit)&&Number.isFinite(age)?'reported':'report_unknown'):live.has(n.id)?'seen':gone.has(n.id)?'lost':'seen';}
    return{nodes,labels,edges,reports,gateway:hasGateway?gateway:null,receiver:data?.receiver||null};
  }
  const STATES={
    mutual:{color:'#168269',dash:'',label:'双方互证'},
    partial:{color:'#237fbe',dash:'7 4',label:'一侧单向 / 一侧互证'},
    oneway:{color:'#aa7021',dash:'7 4',label:'仅单侧采样'},
    lost:{color:'#b3261e',dash:'2 4',label:'采样时已失效'},
    uplink:{color:'#1f6f78',dash:'1 5',label:'LoRa 上行'}
  };
  function pairs(edges){
    const result=new Map();for(const e of edges){const [a,b]=[e.from,e.to].sort(),key=a+'/'+b;if(!result.has(key))result.set(key,{key,a,b,ab:null,ba:null});result.get(key)[e.from===a?'ab':'ba']=e;}
    return[...result.values()].map(p=>{
      const directions=[p.ab,p.ba].filter(Boolean),both=directions.length===2,states=directions.map(e=>e.state);
      const uplink=directions.some(e=>e.kind==='lora_uplink');
      const allLost=states.every(s=>s==='lost'),allMutual=both&&states.every(s=>s==='bidirectional');
      const name=uplink?'uplink':allLost?'lost':allMutual?'mutual':!both?'oneway':'partial',look=STATES[name];
      return{...p,directions,both,state:name,label:look.label,color:look.color,dash:look.dash};
    });
  }
  return{snapshot,pairs,STATES};
})();

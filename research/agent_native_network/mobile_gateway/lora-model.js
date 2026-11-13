'use strict';
// LoRa transports source snapshots. It never establishes current Wi-Fi freshness.
const MobileLoRaModel=(()=>{
  const clean=x=>String(x||'').trim().toLowerCase(),valid=x=>/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(clean(x));
  const number=x=>Number.isFinite(x)?x:null;
  function snapshot(data,elapsed=0){
    const labels=new Map(),nodes=new Map(),edges=[],reports=[];
    for(const [id,name]of Object.entries(data?.labels||{}))if(valid(id)&&typeof name==='string')labels.set(clean(id),name);
    const member=(id,name)=>{if(!valid(id))return;id=clean(id);if(typeof name==='string'&&name.trim())labels.set(id,name.trim());if(!nodes.has(id))nodes.set(id,{id});};
    for(const item of data?.reports||[]){
      const r=item.report;if(!r||r.frame_schema!=='LRN1'||!valid(r.observer_id))continue;
      const id=clean(r.observer_id),receivedAge=number(item.pc_receive_age_ms),entry={...item,report:r,id,age:receivedAge===null?null:Math.max(0,receivedAge+elapsed)};
      reports.push(entry);member(id,item.label);nodes.get(id).report=entry;
      for(const row of r.neighbors||[]){
        if(!valid(row.peer_id)||clean(row.peer_id)===id)continue;
        const peer=clean(row.peer_id);member(peer,row.label);
        edges.push({from:peer,to:id,state:row.state,age:number(row.seen_age_ms),ageLowerBound:null,ageUpperBound:null,rssi:number(row.rssi_dbm),rssiAge:number(row.rf_age_ms),sampleFreshness:'unknown',sampleStale:false,observerStale:false,hasObservation:true,mutual:false,rf_source:'LoRa回传的 ESP-NOW 采样',raw:row,loraReport:entry});
      }
    }
    // A member is "reported" when its own LoRa report arrived, "seen" when only other
    // observers list it as still valid, and "lost" when every row about it is lost.
    const live=new Set(),gone=new Set();
    for(const e of edges){(e.state==='lost'?gone:live).add(e.from);(e.state==='lost'?gone:live).add(e.to);}
    for(const n of nodes.values())n.status=n.report?'reported':live.has(n.id)?'seen':gone.has(n.id)?'lost':'seen';
    return{nodes,labels,edges,reports,receiver:data?.receiver||null};
  }
  const STATES={mutual:{color:'#168269',dash:'',label:'双方互证'},partial:{color:'#237fbe',dash:'7 4',label:'一侧单向 / 一侧互证'},oneway:{color:'#aa7021',dash:'7 4',label:'仅单侧采样'},lost:{color:'#b3261e',dash:'2 4',label:'采样时已失效'}};
  function pairs(edges){
    const result=new Map();for(const e of edges){const [a,b]=[e.from,e.to].sort(),key=a+'/'+b;if(!result.has(key))result.set(key,{key,a,b,ab:null,ba:null});result.get(key)[e.from===a?'ab':'ba']=e;}
    return[...result.values()].map(p=>{
      const directions=[p.ab,p.ba].filter(Boolean),both=directions.length===2,states=directions.map(e=>e.state);
      const allLost=states.every(s=>s==='lost'),allMutual=both&&states.every(s=>s==='bidirectional');
      const name=allLost?'lost':allMutual?'mutual':!both?'oneway':'partial',look=STATES[name];
      return{...p,directions,both,state:name,label:look.label,color:look.color,dash:look.dash};
    });
  }
  return{snapshot,pairs,STATES};
})();

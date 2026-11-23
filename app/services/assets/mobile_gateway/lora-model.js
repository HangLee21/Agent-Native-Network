'use strict';
// LoRa transports source snapshots. It never establishes current Wi-Fi freshness.
const MobileLoRaModel=(()=>{
  const clean=x=>String(x||'').trim().toLowerCase(),valid=x=>/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(clean(x));
  // Receiver identity is supplied by the adapter; it is not necessarily a node MAC.
  const validLabelId=x=>typeof x==='string'&&x.trim().length>0;
  const number=x=>Number.isFinite(x)?x:null;
  function snapshot(data,elapsed=0,registered=[],interrupted=false){
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
      const id=clean(r.observer_id),receivedAge=number(item.pc_receive_age_ms),raw=item.lora||{};
      const datarate=typeof (raw.datarate??raw.datr)==='string'?(raw.datarate??raw.datr):null;
      const parsed=datarate?.match(/^SF(5|6|7|8|9|10|11|12)BW(125|250|500)$/i),cr=raw.coding_rate??raw.codr;
      const lora={...raw,rssi_dbm:raw.rssi_dbm??raw.rssi??null,snr_db:raw.snr_db??raw.lsnr??null,
        channel:raw.channel??raw.chan??null,frequency_hz:Number.isFinite(raw.frequency_hz)&&raw.frequency_hz>0?raw.frequency_hz:Number.isFinite(raw.freq)&&raw.freq>0?Math.round(raw.freq*1000000):null,
        datarate,sf:Number.isInteger(raw.sf)&&raw.sf>=5&&raw.sf<=12?raw.sf:parsed?Number(parsed[1]):null,
        bandwidth_hz:Number.isFinite(raw.bandwidth_hz)&&raw.bandwidth_hz>0?raw.bandwidth_hz:parsed?Number(parsed[2])*1000:null,
        coding_rate:typeof cr==='string'&&/^4\/[5-8]$/.test(cr)?cr:Number.isInteger(cr)&&cr>=5&&cr<=8?'4/'+cr:null,rf_chain:raw.rf_chain??raw.rfch??null};
      const entry={...item,lora,report:r,id,age:receivedAge===null?null:Math.max(0,receivedAge+elapsed)};
      reports.push(entry);member(id,item.label);nodes.get(id).report=entry;
      for(const original of r.neighbors||[]){
        const bits=Number.isInteger(original.valid)?original.valid:Number.isInteger(original.valid_flags)?original.valid_flags:null;
        const present=bit=>bits===null||(bits&bit)!==0;
        const channel=original.wifi_channel??original.channel??null;
        const row={...original,state:original.state==='bidirectional'&&!present(1)?'unknown':original.state,ack_age_ms:present(1)?original.ack_age_ms??null:null,rssi_dbm:present(2)?original.rssi_dbm??original.wifi_rssi_dbm??null:null,rf_age_ms:present(4)?original.rf_age_ms??null:null,wifi_channel:present(8)&&Number.isInteger(channel)&&channel>0?channel:null};
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
    for(const id of registered)member(id);
    for(const n of nodes.values()){
      const raw=data?.receiver?.recent_threshold_ms,period=n.report?.report?.report_period_ms;
      const limit=data?.receiver?.mode==='node_serial'?Math.max(35000,3*(Number.isFinite(period)&&period>0?period:10000)+5000):Number.isFinite(raw)&&raw>0?raw:30000;
      const age=n.report?.age,observed=data?.receiver?.gateway_observed,broken=interrupted||observed===false;
      n.status=n.gateway?(broken?'gateway_offline':'gateway'):n.report?(broken?'interrupted':Number.isFinite(age)&&age>limit?'stale_report':observed===true&&Number.isFinite(age)?'reported':'report_unknown'):'never';n.timeout=limit;
    }
    for(const e of edges){const observer=nodes.get(e.kind==='lora_uplink'?e.from:e.to);e.historical=!observer||observer.status!=='reported';if(!observer?.report&&e.kind!=='lora_uplink')e.historical=true;}
    for(const e of edges){if(e.kind==='lora_uplink')continue;const n=nodes.get(e.from);if(n&&!n.report&&!n.gateway){if(!e.historical&&e.state!=='lost')n.status='seen';else if(n.status==='never')n.status=e.historical?'seen_history':'lost';}}
    return{nodes,labels,edges,reports,gateway:hasGateway?gateway:null,receiver:data?.receiver||null};
  }
  const STATES={
    mutual:{color:'#168269',dash:'',label:'双方互证'},
    partial:{color:'#237fbe',dash:'7 4',label:'一侧单向 / 一侧互证'},
    oneway:{color:'#aa7021',dash:'7 4',label:'仅单侧采样'},
    lost:{color:'#b3261e',dash:'2 4',label:'采样时已失效'},
    uplink:{color:'#1f6f78',dash:'1 5',label:'LoRa 上行'},
    historical:{color:'#919b9e',dash:'2 6',label:'历史记录 · 当前不可确认'}
  };
  function pairs(edges){
    const result=new Map();for(const e of edges){const [a,b]=[e.from,e.to].sort(),key=(e.kind==='lora_uplink'?'lora:':'wifi:')+a+'/'+b;if(!result.has(key))result.set(key,{key,a,b,ab:null,ba:null});result.get(key)[e.from===a?'ab':'ba']=e;}
    return[...result.values()].map(p=>{
      const directions=[p.ab,p.ba].filter(Boolean),both=directions.length===2,states=directions.map(e=>e.state);
      const uplink=directions.some(e=>e.kind==='lora_uplink');
      const allLost=states.every(s=>s==='lost'),allMutual=both&&states.every(s=>s==='bidirectional');
      const historical=directions.some(e=>e.historical);const name=historical?'historical':uplink?'uplink':allLost?'lost':allMutual?'mutual':!both?'oneway':'partial',look=STATES[name];
      return{...p,directions,both,state:name,label:look.label,color:look.color,dash:look.dash};
    });
  }
  return{snapshot,pairs,STATES};
})();

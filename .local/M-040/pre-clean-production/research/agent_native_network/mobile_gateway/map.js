'use strict';
// MOBILE_MAP_MODEL_BEGIN — no DOM, network, radio operations or route computation.
const MobileMapModel=(()=>{
  const R=6371008.8,rad=Math.PI/180,MAC=/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/;
  const clean=x=>String(x||'').trim().toLowerCase(),number=x=>typeof x==='number'&&Number.isFinite(x);
  function project(p,origin){return{x:R*rad*(p.lon-origin.lon)*Math.cos(origin.lat*rad),y:R*rad*(p.lat-origin.lat)};}
  function unproject(p,origin){return{lat:origin.lat+p.y/R/rad,lon:origin.lon+p.x/(R*rad*Math.cos(origin.lat*rad))};}
  function validPosition(p){return p&&number(p.lat)&&number(p.lon)&&Math.abs(p.lat)<=85&&Math.abs(p.lon)<=180&&p.valid!==false&&number(p.age_ms)&&p.age_ms>=0;}
  const kind=e=>String(e.event||e.type||e.kind||'unknown');
  function eventInfo(e){
    const k=kind(e);
    if(k==='tx_submit'&&(e.kind==='control'||e.packet_kind&&e.packet_kind!=='DATA'))return{group:'network',name:'控制帧本地提交',color:'gray'};
    if(k==='route_selected')return{group:'route',name:'板端选择',color:'purple'};
    if(k==='tx_queued')return{group:'data',name:'源端接纳入队',color:'blue'};
    if(k==='tx_submit')return{group:'data',name:'本板提交',color:'blue'};
    if(k==='tx_link_ok')return{group:'data',name:'本跳链路回调',color:'blue'};
    if(k==='tx_api_failed')return{group:'data',name:'本跳 API 提交失败',color:'red'};
    if(k==='rx_relay')return{group:'data',name:'中继本地收到',color:'blue'};
    if(k==='rx_local'){
      const reporter=clean(e.reporter||e.node_id),valid=reporter===clean(e.dst)&&(!e.node_id||clean(e.node_id)===reporter)&&(!e.observer_id||clean(e.observer_id)===reporter)&&MAC.test(reporter)&&MAC.test(clean(e.origin))&&Number.isInteger(e.origin_boot??e.boot)&&(e.origin_boot??e.boot)>0&&Number.isInteger(e.seq)&&e.seq>0&&typeof e.payload_hex==='string'&&/^(?:[0-9a-f]{2}){0,160}$/i.test(e.payload_hex);
      return{group:'data',name:valid?'目的本地收到':'目的收件字段不完整',color:valid?'green':'red',destinationEvidence:valid};
    }
    if(/route_no_route|delivery_unknown|route_drop|tx_link_fail/.test(k))return{group:'data',name:{route_no_route:'板端无路',delivery_unknown:'交付未知',route_drop:'板端丢弃',tx_link_fail:'本跳链路失败'}[k],color:'red'};
    const names={gateway_started:'观测网关启动',report:'收到遥测报告',session_changed:'报告会话已变化',telemetry_rejoined:'报告重新上线',report_online:'报告上线',report_offline:'观测报告失联',report_reconnected:'报告重新上线',boot_changed:'板启动已变化',neighbor_heard:'单向听到',neighbor_confirmed:'无线双向确认',neighbor_lost:'无线邻居失效',route_invalidated:'板端路径失效',position_stale:'GPS过期',position_unknown:'GPS未知'};
    return{group:'network',name:names[k]||k,color:/lost|offline|invalidated/.test(k)?'red':'gray'};
  }
  function create(){return{nodes:new Map(),events:[],seen:new Set(),retired:new Map(),receivedAt:0,server:null};}
  function list(state){const raw=state.nodes??state.reports??[];return Array.isArray(raw)?raw:Object.entries(raw).map(([id,r])=>({node_id:id,...r}));}
  function ageOf(raw,state){
    for(const v of [raw.report_age_ms,raw.received_age_ms,raw.age_ms])if(number(v))return Math.max(0,v);
    const now=state.now_ms??state.server_time_ms??state.gateway_time_ms;
    const received=raw.received_at_ms??raw.gateway_received_at_ms;
    if(number(now)&&number(received))return Math.max(0,now-received);
    if(typeof raw.received_at==='string'&&typeof state.generated_at==='string'){const delta=Date.parse(state.generated_at)-Date.parse(raw.received_at);if(Number.isFinite(delta))return Math.max(0,delta);}
    return 0; // arrival of this snapshot, never a subtraction of two node clocks
  }
  function addEvent(model,e,key){if(model.seen.has(key))return;model.seen.add(key);model.events.push({...e,_key:key});if(model.events.length>1000)model.events.shift();if(model.seen.size>4000)model.seen=new Set(model.events.map(e=>e._key));}
  function apply(model,state,at=0){
    if(!state||typeof state!=='object')throw Error('网关状态不是JSON对象');
    model.receivedAt=at;model.server=state;const present=new Set(),observedTime=state.gateway_instance&&number(state.now_ms)?{received_ms:state.now_ms}:{at_ms:state.elapsed_ms??at};
    for(const raw of list(state)){
      const r=raw.report||raw.latest_report||raw,id=clean(r.node_id||raw.node_id);if(!MAC.test(id))continue;present.add(id);
      const previous=model.nodes.get(id),session=String(r.session_id??''),boot=String(r.boot_id??''),incarnation=boot+'/'+session;
      if(model.retired.get(id)?.has(incarnation))continue;
      if(previous&&previous.incarnation===incarnation&&number(r.seq)&&number(previous.seq)&&r.seq<previous.seq)continue;
      const changed=previous&&previous.incarnation!==incarnation;
      if(changed){if(!model.retired.has(id))model.retired.set(id,new Set());model.retired.get(id).add(previous.incarnation);addEvent(model,{event:previous.boot_id!==r.boot_id?'boot_changed':'report_reconnected',reporter:id,label:r.label,...observedTime},'session/'+id+'/'+incarnation);}
      const n={...r,id,incarnation,online:raw.telemetry_status?raw.telemetry_status==='online':raw.online??raw.observation_online??r.online,projectedAges:!!state.gateway_instance,offline_after_ms:state.offline_after_ms??30000,stale_after_ms:state.stale_after_ms??30000,report_age_ms:ageOf(raw,state),loadedAt:at,history:previous?.history||[]};
      if(n.online===undefined&&['offline','stale','lost'].includes(raw.observation_state))n.online=false;
      if(previous?.online===false&&n.online!==false&&!changed)addEvent(model,{event:'report_reconnected',reporter:id,label:r.label,...observedTime},'reconnected/'+id+'/'+r.seq);
      if(previous&&previous.online!==false&&n.online===false)addEvent(model,{event:'report_offline',reporter:id,label:r.label,...observedTime},'offline/'+id+'/'+r.seq);
      if(!previous)addEvent(model,{event:'report_online',reporter:id,label:r.label,...observedTime},'online/'+id+'/'+incarnation);
      const fresh=!previous||changed||r.seq!==previous.seq;
      if(fresh)for(const peer of r.neighbors||[]){const peerId=clean(peer.peer_id??peer.node_id),old=previous?.neighbors?.find(x=>clean(x.peer_id??x.node_id)===peerId);if(old?.state!==peer.state){const event=peer.state==='lost'?'neighbor_lost':['confirmed','bidirectional'].includes(peer.state)?'neighbor_confirmed':'neighbor_heard';addEvent(model,{event,reporter:id,peer_id:peerId,...observedTime,derived_from:'report_snapshot_change'},'neighbor/'+id+'/'+incarnation+'/'+r.seq+'/'+peerId+'/'+peer.state);}}
      if(validPosition(r.position)&&fresh){n.history=[...n.history,{...r.position,segment:incarnation}].slice(-180);}
      model.nodes.set(id,n);
      if(!state.gateway_instance)for(const e of r.events||[]){const item={...e,reporter:id,report_label:r.label,rf_source:e.rf_source??r.rf_source};addEvent(model,item,e.event_id||id+'/'+incarnation+'/'+JSON.stringify(e));}
    }
    for(const e of state.events||state.timeline||[]){const raw=e.data??e,reporter=clean(e.reporter||e.node_id||e.observer_id||raw.observer_id);addEvent(model,{...(raw.raw||raw),...raw,event:e.type||raw.event||raw.type,reporter,received_ms:e.received_ms??raw.received_ms},e.cursor!==undefined?'gateway/'+state.gateway_instance+'/'+e.cursor:e.event_id||e.id||'gateway/'+JSON.stringify(e));}
    return model;
  }
  function reportAge(n,now){return n.report_age_ms+Math.max(0,now-n.loadedAt);}
  function online(n,now,timeout=n.offline_after_ms??30000){return n.online!==false&&reportAge(n,now)<=timeout;}
  function positionState(n,now,timeout=n.stale_after_ms??30000){if(!validPosition(n.position))return{valid:false,reason:'无有效GPS'};const age=n.position.age_ms+(n.projectedAges?Math.max(0,now-n.loadedAt):reportAge(n,now)),stale=n.position.stale===true||age>timeout;return{valid:!stale,age,reason:stale?'GPS已过期':''};}
  function edges(model,now){
    if(model.server?.gateway_instance&&Array.isArray(model.server.edges)){
      const elapsed=Math.max(0,now-model.receivedAt),result=model.server.edges.map(r=>{
        const reporter=model.nodes.get(clean(r.to)),sampleAge=number(r.sample_age_ms)&&r.age_is_lower_bound!==true?r.sample_age_ms+elapsed:null;
        const lower=r.sample_age_lower_bound_ms??(r.age_is_lower_bound===true?r.sample_age_ms:null),rssiLower=number(lower)?lower+elapsed:null,upper=number(r.sample_age_upper_bound_ms)?r.sample_age_upper_bound_ms+elapsed:null;
        const measured=upper??sampleAge,expired=measured!==null&&measured>(model.server.stale_after_ms??30000),declared=['fresh','stale','unknown'].includes(r.sample_freshness)?r.sample_freshness:null;
        let freshness=expired||r.invalidated_reason?'stale':declared??(sampleAge!==null&&r.sample_stale!==true?'fresh':sampleAge===null?'unknown':'stale'),state=r.state==='confirmed'?'bidirectional':r.state,age=sampleAge,ageLowerBound=rssiLower,ageUpperBound=upper,directEvidence=null,directConfirmed=false;
        if(r.direct_evidence){
          const p=r.direct_evidence,seen=number(p.seen_age_upper_bound_ms)?p.seen_age_upper_bound_ms+elapsed:null,ack=number(p.confirmation_age_upper_bound_ms)?p.confirmation_age_upper_bound_ms+elapsed:null;
          const valid=p.epoch_verified===true&&p.valid===true&&p.freshness==='fresh'&&['heard','bidirectional'].includes(p.state)&&seen!==null&&seen<(p.seen_limit_ms??12000);
          directConfirmed=valid&&p.confirmed===true&&p.state==='bidirectional'&&ack!==null&&ack<(p.confirmation_limit_ms??9000);
          freshness=valid?'fresh':p.state==='unknown'?'unknown':'stale';if(p.state!=='unknown')state=p.state;
          const seenLower=number(p.seen_age_lower_bound_ms)?p.seen_age_lower_bound_ms+elapsed:null,ackLower=number(p.confirmation_age_lower_bound_ms)?p.confirmation_age_lower_bound_ms+elapsed:null;
          directEvidence={...p,seen_age_upper_bound_ms:seen,confirmation_age_upper_bound_ms:ack,seen_age_lower_bound_ms:seenLower,confirmation_age_lower_bound_ms:ackLower,valid,confirmed:directConfirmed};age=null;ageLowerBound=seenLower;ageUpperBound=seen;
        }
        const fresh=freshness==='fresh',observerReportOnline=!!reporter&&online(reporter,now,model.server.offline_after_ms??30000),reporterOnline=fresh&&(declared==='fresh'||directEvidence!==null)||observerReportOnline;
        const hasObservation=state!=='unknown'||r.sample_received_ms!=null||number(r.rssi_dbm)||!!directEvidence&&directEvidence.state!=='unknown';
        const mutualRemaining=number(r.mutual_valid_for_ms)?Math.max(0,r.mutual_valid_for_ms-elapsed):null,rssiUpper=number(r.rssi_sample_age_upper_bound_ms)?r.rssi_sample_age_upper_bound_ms+elapsed:upper;
        return{from:clean(r.from),to:clean(r.to),state,rssi:number(r.rssi_dbm)?r.rssi_dbm:null,age,ageLowerBound,ageUpperBound,rf_source:r.rf_source,observerReportOnline,reporterOnline,mutual:r.mutual_confirmed===true&&fresh&&reporterOnline&&(!directEvidence||directConfirmed)&&(mutualRemaining===null||mutualRemaining>0),mutualRemaining,sampleStale:freshness==='stale',sampleFreshness:freshness,directEvidence,directConfirmed,hasObservation,rssiAge:sampleAge,rssiLowerBound:rssiLower,rssiUpperBound:rssiUpper,rssiFreshness:r.rssi_sample_freshness??r.sample_freshness,raw:r};
      });
      for(const e of result)if(e.directEvidence)e.mutual=e.mutual&&result.some(reverse=>reverse.from===e.to&&reverse.to===e.from&&reverse.directConfirmed);
      return result;
    }
    const out=[];for(const n of model.nodes.values())for(const r of n.neighbors||[]){const peer=clean(r.peer_id??r.node_id);if(!MAC.test(peer)||peer===n.id)continue;
      out.push({from:peer,to:n.id,state:r.state||'unknown',rssi:number(r.rssi_dbm)?r.rssi_dbm:null,age:number(r.sample_age_ms)?r.sample_age_ms+reportAge(n,now):null,rf_source:r.rf_source??n.rf_source??'unavailable',reporterOnline:online(n,now),peer,raw:r});
    }
    for(const e of out){const reverse=out.find(r=>r.from===e.to&&r.to===e.from);e.mutual=e.state==='bidirectional'&&reverse?.state==='bidirectional'&&e.reporterOnline&&reverse.reporterOnline;}
    return out;
  }
  function bounds(nodes,origin){const points=nodes.filter(n=>validPosition(n.position)).map(n=>project(n.position,origin));if(!points.length)return{x:-300,y:-200,w:600,h:400};const xs=points.map(p=>p.x),ys=points.map(p=>p.y),w=Math.max(120,Math.max(...xs)-Math.min(...xs)),h=Math.max(100,Math.max(...ys)-Math.min(...ys));return{x:(Math.max(...xs)+Math.min(...xs))/2-w*.65,y:(Math.max(...ys)+Math.min(...ys))/2-h*.65,w:w*1.3,h:h*1.3};}
  return{create,apply,project,unproject,validPosition,positionState,reportAge,online,edges,eventInfo,bounds,clean};
})();
// MOBILE_MAP_MODEL_END

'use strict';
// Pure presentation helpers: no route solver, transport, coordinates or side effects.
const MobileStudioModel=(()=>{
  const mac=x=>String(x||'').trim().toLowerCase(),isMAC=x=>/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(mac(x))||/^[0-9a-f]{16}$/.test(mac(x));
  const hash=x=>{let h=2166136261;for(const c of x)h=Math.imul(h^c.charCodeAt(0),16777619);return h>>>0;};
  function topology(ids,edges,previous=new Map()){
    const ordered=[...new Set(ids.map(mac).filter(isMAC))].sort().slice(0,128),points=new Map();
    for(const id of ordered){const old=previous.get(id),h=hash(id);points.set(id,old?{...old}:{x:((h%997)/997-.5)*540,y:(((h>>>10)%991)/991-.5)*330});}
    const links=edges.filter(e=>e.state!=='lost'&&points.has(e.from)&&points.has(e.to));
    for(let iteration=0;iteration<75;iteration++){
      const force=new Map(ordered.map(id=>[id,{x:0,y:0}]));
      for(let i=0;i<ordered.length;i++)for(let j=i+1;j<ordered.length;j++){
        const a=points.get(ordered[i]),b=points.get(ordered[j]);let dx=a.x-b.x,dy=a.y-b.y;if(Math.hypot(dx,dy)<.1){dx=1;dy=.7;}
        const d=Math.max(18,Math.hypot(dx,dy)),strength=6500/(d*d),f=force.get(ordered[i]),g=force.get(ordered[j]);f.x+=dx/d*strength;f.y+=dy/d*strength;g.x-=dx/d*strength;g.y-=dy/d*strength;
      }
      for(const e of links){const a=points.get(e.from),b=points.get(e.to),dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),f=force.get(e.from),g=force.get(e.to),k=(d-145)*.013;f.x+=dx/d*k;f.y+=dy/d*k;g.x-=dx/d*k;g.y-=dy/d*k;}
      for(const id of ordered){const p=points.get(id),f=force.get(id);p.x+=Math.max(-6,Math.min(6,f.x-p.x*.003));p.y+=Math.max(-6,Math.min(6,f.y-p.y*.003));}
    }
    return points;
  }
  function packetKey(e){const b=e.origin_boot??e.boot;return isMAC(e.origin)&&isMAC(e.dst)&&Number.isInteger(b)&&b>0&&Number.isInteger(e.seq)&&e.seq>0?[mac(e.origin),b,e.seq,mac(e.dst)].join('/'):null;}
  function payload(hex){if(typeof hex!=='string'||!/^(?:[0-9a-f]{2}){0,160}$/i.test(hex))return null;try{return new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(hex.match(/../g)||[],x=>parseInt(x,16)));}catch{return null;}}
  function packets(events,eventInfo){
    const rows=new Map();
    for(const e of events){const type=e.event||e.type;
      if(e.kind==='control'||e.packet_kind&&e.packet_kind!=='DATA'||e.sequence_scope==='route_request')continue;
      if(!['tx_queued','tx_submit','tx_link_ok','rx_relay','rx_local','route_selected','route_no_route','route_drop','delivery_unknown','tx_link_fail','tx_api_failed','send_rejected','route_rejected'].includes(type))continue;
      const key=packetKey(e);if(!key)continue;
      if(!rows.has(key))rows.set(key,{key,origin:mac(e.origin),origin_boot:e.origin_boot??e.boot,seq:e.seq,dst:mac(e.dst),events:[],segments:[],routes:[],payloads:[],received:false});
      const row=rows.get(key),reporter=mac(e.reporter||e.node_id);row.events.push(e);row.last=e;
      if(typeof e.payload_hex==='string'&&/^(?:[a-f0-9]{2}){0,160}$/i.test(e.payload_hex)&&!row.payloads.includes(e.payload_hex.toLowerCase()))row.payloads.push(e.payload_hex.toLowerCase());
      if(type==='route_selected'&&Array.isArray(e.path)&&e.path.length>1&&e.path.every(isMAC))row.routes.push({path:e.path.map(mac),event:e});
      let from,to;
      if(type==='tx_submit'){from=reporter;to=mac(e.next_hop);}
      if(type==='rx_relay'||type==='rx_local'){from=mac(e.previous_hop);to=reporter;}
      if(isMAC(from)&&isMAC(to)&&from!==to)row.segments.push({from,to,event:e,type});
      if(eventInfo(e).destinationEvidence===true)row.received=true;
    }
    return [...rows.values()].slice(-64).reverse().map(r=>{
      const delivery=r.received?(r.payloads.length>1?'payload_conflict':'destination_received'):'unconfirmed';
      return{...r,bytesMatch:r.payloads.length===1,delivery,...packetState({...r,delivery})};
    });
  }
  function packetState(row){
    const has=kind=>row.events.some(e=>(e.event||e.type)===kind),sourceEvents=row.events.filter(e=>mac(e.reporter||e.node_id)===row.origin&&((e.observer_boot??e.entry_boot??e.boot_id)==null||(e.observer_boot??e.entry_boot??e.boot_id)===row.origin_boot)),submitted=has('tx_submit')||has('rx_relay')||has('tx_link_ok');
    if(row.delivery==='payload_conflict')return{state:'payload_conflict',stateLabel:'目的收件字节冲突',reason:'同一原包身份出现不同载荷，保留冲突原字节，不标为一致交付。'};
    if(row.delivery==='destination_received')return{state:'destination_received',stateLabel:'目的实收原字节',reason:'目的节点自己的 rx_local 含完整原包身份和载荷；后到的本跳失败不会撤销这条收件证据。'};
    const noRoute=sourceEvents.find(e=>(e.event||e.type)==='route_no_route'&&e.reason!==6);
    if(noRoute&&!submitted)return{state:'no_route',stateLabel:'板端本轮无路',reason:'源端明确报告该包本轮未找到路；当前未观测到目的收件，不据此推断后续新业务。'};
    const rejected=sourceEvents.some(e=>['send_rejected','route_rejected','route_drop'].includes(e.event||e.type));
    if(rejected&&!submitted)return{state:'rejected',stateLabel:'源端拒绝 / 本地丢弃',reason:'源端有明确拒绝或本地丢弃记录；不是对所有沿途和后续业务的永久失败判定。'};
    if(has('delivery_unknown')||has('tx_link_fail')||has('tx_api_failed')||has('route_drop')||noRoute||rejected||sourceEvents.some(e=>(e.event||e.type)==='route_no_route'&&e.reason===6))return{state:'delivery_unknown',stateLabel:'最终交付未知',reason:has('tx_link_fail')||has('tx_api_failed')?'已见本跳发送失败，但一次回调不能证明目的端从未收到；仍须核对目的原始收件。':noRoute||rejected?'已见提交或中继，又有局部无路/拒绝记录；现有观察不足以确定最终交付。':has('route_drop')?'中间节点报告本地丢弃，当前缺目的收件；保留为最终交付未知。':'板端报告交付未知或源端取消；不归为确定丢包。'};
    if(has('rx_relay')||has('tx_submit')||has('tx_link_ok'))return{state:'awaiting_receipt',stateLabel:has('rx_relay')?'已见中继，待目的收件':'已提交，待目的收件',reason:has('rx_relay')?'中继已有本地收到证据，仍未观测到匹配的目的 rx_local。':'仅有本跳提交或链路回调，仍未观测到匹配的目的 rx_local。'};
    if(sourceEvents.some(e=>(e.event||e.type)==='tx_queued'))return{state:'queued',stateLabel:'仅排队，未见提交',reason:'源端仅接纳入队；尚未观测到该包提交或中继收件。'};
    return{state:'observed',stateLabel:'仅见选路，未见提交',reason:'目前只有选路或其他局部记录，缺业务提交和目的收件证据。'};
  }
  function createPacketLog(){return{rows:new Map(),seen:new Set(),seenOrder:[],ordinal:0};}
  function mergePackets(log,events,eventInfo,coverage={}){
    for(const e of events){
      const projected=packets([e],eventInfo)[0];if(!projected)continue;
      const eventKey=e._key||e.event_id||JSON.stringify(e);if(log.seen.has(eventKey))continue;
      log.seen.add(eventKey);log.seenOrder.push(eventKey);if(log.seenOrder.length>8192)log.seen.delete(log.seenOrder.shift());
      let record=log.rows.get(projected.key);if(!record){record={events:[],gaps:new Set(),ordinal:0,payloadEvidence:new Map(),receipt:null};log.rows.set(projected.key,record);}
      if(eventInfo(e).destinationEvidence===true)record.receipt=e;
      if(typeof e.payload_hex==='string'&&/^(?:[a-f0-9]{2}){0,160}$/i.test(e.payload_hex)&&!record.payloadEvidence.has(e.payload_hex.toLowerCase())){if(record.payloadEvidence.size<2)record.payloadEvidence.set(e.payload_hex.toLowerCase(),e);else record.gaps.add('不同原字节超过两种，仅保留前两种冲突样本');}
      record.events.push(e);if(record.events.length>48){record.events.splice(1,1);record.gaps.add('本页该包观察记录已达48条保留上限');}
      record.ordinal=++log.ordinal;
      if(e.record_overwritten>0)record.gaps.add('观察节点 RAM 有累计覆盖，是否影响本条无法确定');
      if(coverage.timelineTruncated)record.gaps.add('网关较早时间线超出保留范围');
      const ids=new Set([projected.origin,projected.dst,...record.events.map(x=>mac(x.reporter||x.node_id))]);
      for(const n of coverage.nodes||[]){if(!ids.has(mac(n.id||n.node_id)))continue;const a=n.agent||{};if(a.record_overwritten>0)record.gaps.add('相关节点 RAM 有累计覆盖，是否影响本条无法确定');if(a.sampled_records_skipped>0)record.gaps.add('相关节点报告含抽样跳过，观察不完整');if(n.events_dropped>0)record.gaps.add('节点事件报告有溢出计数');}
      if(log.rows.size>128){const oldest=[...log.rows].filter(([key])=>key!==coverage.pinnedKey).sort((a,b)=>a[1].ordinal-b[1].ordinal)[0][0];log.rows.delete(oldest);}
    }
    return [...log.rows.values()].sort((a,b)=>b.ordinal-a.ordinal).map(record=>{const evidence=[...new Set([...record.events,...record.payloadEvidence.values(),...(record.receipt?[record.receipt]:[])])],row=packets(evidence,eventInfo)[0];return{...row,coverageNotes:[...record.gaps],last:record.events.at(-1)};});
  }
  function edgeInfo(edge){
    if(edge.state==='lost')return{state:'lost',label:'无线失效（节点报告）',color:'red',dashed:true};
    if(edge.reporterOnline===false)return{state:'report_stale',label:'观察者报告陈旧',color:'gray',dashed:true};
    if(edge.sampleStale)return{state:'expired',label:'样本过期',color:'gray',dashed:true};
    if(edge.sampleFreshness==='fresh')return edge.mutual?{state:'mutual',label:'新鲜双向互证',color:'green',dashed:false}:{state:'directed',label:edge.state==='heard'?'新鲜单向收到':'本端新鲜，待对向互证',color:'blue',dashed:false};
    if(!Number.isFinite(edge.age)||edge.sampleFreshness==='unknown')return{state:'unknown_age',label:Number.isFinite(edge.ageLowerBound)?'方向已观测，年龄仅下界':'样本年龄未知，不判有效',color:'gray',dashed:true};
    if(edge.mutual)return{state:'mutual',label:'新鲜双向互证',color:'green',dashed:false};
    return{state:'directed',label:edge.state==='heard'?'单向收到':'本端确认，待对向互证',color:'blue',dashed:true};
  }
  function edgePairs(edges){
    const pairs=new Map();for(const edge of edges){if(edge.hasObservation===false||!isMAC(edge.from)||!isMAC(edge.to)||edge.from===edge.to)continue;const [a,b]=[edge.from,edge.to].sort(),key=a+'/'+b;if(!pairs.has(key))pairs.set(key,{key,a,b,ab:null,ba:null});pairs.get(key)[edge.from===a?'ab':'ba']=edge;}
    return [...pairs.values()].map(pair=>{
      const directions=[pair.ab,pair.ba].filter(Boolean),active=directions.filter(e=>!['lost','expired','report_stale'].includes(edgeInfo(e).state)),draw=active.length?active:directions,both=draw.length===2,infos=draw.map(edgeInfo),allStale=active.length===0,mutual=both&&infos.every(i=>i.state==='mutual');
      const singleFresh=!both&&!allStale&&(draw[0].sampleFreshness==='fresh'||Number.isFinite(draw[0].age)&&draw[0].sampleFreshness!=='unknown')&&!draw[0].sampleStale;
      const state=allStale?'stale':mutual?'mutual':both?'both_unknown':singleFresh?'single_fresh':'single_unknown';
      const styles={stale:{label:'过期 / 失联旧观测',color:'#a7b1b5',dash:'2 7'},mutual:{label:'新鲜双向互证',color:'#168269',dash:''},both_unknown:{label:'曾双向 · 当前未知',color:'#8056ad',dash:'9 5'},single_fresh:{label:'新鲜单向观测',color:'#237fbe',dash:''},single_unknown:{label:'单向观测 · 当前未知',color:'#aa7021',dash:'9 5'}};
      return{...pair,ab:draw.find(e=>e.from===pair.a)||null,ba:draw.find(e=>e.from===pair.b)||null,directions,observedBoth:directions.length===2,both,state,...styles[state]};
    });
  }
  function pairGeometry(a,b){
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy),ux=d?dx/d:1,uy=d?dy/d:0,px=-uy,py=ux;
    if(d>=120)return{tag:'line',attrs:{x1:a.x+ux*40,y1:a.y+uy*40,x2:b.x-ux*40,y2:b.y-uy*40},label:{x:(a.x+b.x)/2+px*14,y:(a.y+b.y)/2+py*14}};
    const spread=d<1?30:0,start={x:a.x+px*40-ux*spread,y:a.y+py*40-uy*spread},end={x:b.x+px*40+ux*spread,y:b.y+py*40+uy*spread};
    return{tag:'path',attrs:{d:`M ${start.x} ${start.y} C ${start.x+px*90} ${start.y+py*90} ${end.x+px*90} ${end.y+py*90} ${end.x} ${end.y}`,fill:'none'},start,end,label:{x:(a.x+b.x)/2+px*120,y:(a.y+b.y)/2+py*120}};
  }
  function fieldHealth({studio=null,controller={},upstream={},nodeCount=0,edgeCount=0,snapshotLoaded=false,snapshotError='',external=false}={}){
    const item=(state,title,next,warning=false)=>({state,title,next,warning});
    if(studio?.mode==='demo')return item('demo',studio.demo?.running?'软件演示运行中':'软件演示尚未运行','只有点击启动才运行模拟节点；现场业务数据不会混入演示。');
    if(snapshotError)return item('snapshot_error','现场快照暂时读取失败','页面会自动重连；已有图形是上次记录，不能据此判断板子或无线已断开。',true);
    if(!external&&controller.available!==true&&!controller.legacy){
      if(controller.checking&&controller.available===null)return item('starting','正在连接现场服务','请稍候；若持续无法连接，请双击统一现场启动器。本页会自动重连。');
      return item('controller_unreachable','现场页面服务暂时不可连接','请用统一现场启动器恢复服务；本页自动重连，保留你的布局和筛选。',true);
    }
    if(!external&&controller.available===true){
      if(upstream.state==='checking')return item('starting','正在连接上游业务服务','请稍候；页面会自动更新，无需切换软件演示。');
      if(upstream.state==='unreachable')return item('upstream_unreachable','上游业务服务未连接','请用统一现场启动器启动或恢复业务服务。本页会自动重连；已有图形仅是上次记录。',true);
      if(studio?.error)return item('observation_error','业务服务在线，节点观测查询暂未成功','请确认板子供电及热点连接；页面会继续查询，保留已收到的记录。',true);
    }
    if(!snapshotLoaded)return item('starting','正在读取节点报告','请稍候；节点、定位和无线关系会随实际报告出现。');
    if(!nodeCount)return item('waiting_boards','观测服务在线，尚无板子报告','请确认板子已供电并接入所配置的热点；有报告后会自动显示。');
    if(!edgeCount)return item('waiting_rf',`已发现 ${nodeCount} 块板，暂缺 RF 邻居样本`,'可以查看 agent 和收发记录；等待邻居遥测，不从热点连接推算无线边。');
    return item('online',`现场观测在线 · ${nodeCount} 块板 · ${edgeCount} 条有向记录`,'节点、业务与无线观测随报告自动更新；GPS 和 RF 来源分别显示。');
  }
  return{topology,packets,packetKey,payload,isMAC,fieldHealth,createPacketLog,mergePackets,edgeInfo,edgePairs,pairGeometry};
})();

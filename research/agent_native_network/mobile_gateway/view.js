'use strict';
(()=>{
  const M=MobileMapModel,S=MobileStudioModel,L=MobileLoRaModel,$=id=>document.getElementById(id),ns='http://www.w3.org/2000/svg';
  const colors={green:'#17816c',blue:'#4283b0',red:'#c26853',gray:'#91a0a4',purple:'#8759a6'};
  let model=M.create(),selected='',timer=null,observing=true,inFlight=false,version=0,instance=null,cursor=0,baseKey=null;
  let origin=null,view=null,zoom=1,autoFit=true,logical=new Map(),layoutKey='',packetRows=[],selectedPacket='',positions=new Map(),topology=true,animated=new Set(),pendingAnimation=[];
  let snapshotLoaded=false,snapshotError='',health=null,radioExpiry=null;
  let packetLog=S.createPacketLog(),selectedEdge='',timelineTruncated=false;
  let loraData=null,loraReadAt=0,loraError='',loraVersion=0,loraLoading=false;
  let shownSource='wifi';const sourceViews=new Map();
  const isLoRa=()=>$('topologySource').value==='lora';
  // Both sources are legitimate: a serial board relaying LRN1 snapshots, and the Ethernet
  // LoRa gateway (RHF2S008) that receives the same frames directly.
  const LORA_SOURCES=['lora_received_snapshot','gateway_udp_lrn1'];
  const lora=()=>L.snapshot(loraData,Math.max(0,now()-loraReadAt));
  const radioEdges=()=>isLoRa()?lora().edges:M.edges(model,now()).filter(e=>e.hasObservation!==false);
  const graphNodes=()=>isLoRa()?[...lora().nodes.values()].map(n=>({...model.nodes.get(n.id),...n})):[...model.nodes.values()];
  const age=x=>Number.isFinite(x)?x<1000?Math.round(x)+' ms':(x/1000).toFixed(1)+' s':'未知';
  const source=x=>({simulated:'模拟',fake:'模拟',fake_gps:'模拟 GPS',gpsd:'GPSD',gps:'真实 GPS',measured:'实测',unavailable:'不可用',host_model:'主机模型',board_field_agent:'板内发生器',actual_E2_fake_agent_function_processes:'E2 fake_agent 进程',E2_fake_agent_function_host_model:'E2 fake_agent（主机模型）'}[x]||x||'未提供');
  const label=id=>model.nodes.get(M.clean(id))?.label||lora().labels.get(M.clean(id))||M.clean(id).slice(-8)||'未知';
  const text=(id,value)=>$(id).textContent=value,now=()=>performance.now();
  function svg(tag,attrs={},content){const el=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,v);if(content!==undefined)el.textContent=content;return el;}
  function html(tag,content,cls){const e=document.createElement(tag);e.textContent=content;if(cls)e.className=cls;return e;}
  const sampleState=x=>({heard:'采样时单向听到',bidirectional:'采样时本端确认',lost:'采样时已失效'}[x]||'采样状态未知');
  const SAMPLE_COLOR={bidirectional:'#168269',heard:'#237fbe',lost:'#b3261e',unknown:'#a7b1b5'};
  const radioInfo=e=>isLoRa()?{label:sampleState(e.state),color:SAMPLE_COLOR[e.state]||'#8d9a9e'}:S.edgeInfo(e);
  // LoRa legend uses the same colours as the drawn links and node rings.
  function renderLoRaLegend(){
    const box=$('loraLegend');
    if(box.dataset.built==='1')return;
    box.dataset.built='1';box.replaceChildren();
    for(const look of Object.values(L.STATES)){
      const chip=html('span','','legendChip'),bar=html('i','','legendBar');
      bar.style.borderTopColor=look.color;bar.style.borderTopStyle=look.dash?'dashed':'solid';
      chip.append(bar,html('span',look.label));box.append(chip);
    }
    for(const [name,color] of [['节点：LoRa 在线','#8056ad'],['节点：仅被邻居看到','#aa7021'],['节点：采样已失效','#b3261e']]){
      const chip=html('span','','legendChip'),dot=html('i','','legendDot');
      dot.style.background=color;chip.append(dot,html('span',name));box.append(chip);
    }
  }
  function renderLoRa(){
    const enabled=isLoRa(),data=lora();$('loraStatus').classList.toggle('hidden',!enabled);$('wifiLegend').classList.toggle('hidden',enabled);$('loraLegend').classList.toggle('hidden',!enabled);if(!enabled)return;
    renderLoRaLegend();
    const r=data.receiver,offline=['stale','unavailable','busy','error'].includes(r?.state)||!!loraError,stateName={idle:'未开始接收',connecting:'正在连接',receiving:'正在实收',stale:'暂未续收',unavailable:'接收器不可用',busy:'串口已占用',error:'读取异常'};
    $('loraStatus').classList.toggle('warning',offline);text('loraTitle',loraError?'LoRa 来源暂时不可读取':r?`LoRa 接收器 ${r.gateway_id?label(r.gateway_id):'待识别'} · ${stateName[r.state]||'状态未提供'}`:loraLoading?'正在读取 LoRa 来源':'尚无 LoRa 接收器报告');
    text('loraNote',(loraError?loraError+'；保留上次快照。':'')+(r?.error?r.error+'。':'')+`已取得 ${data.reports.length} 个报告者的最近快照。板间箭头为 ESP-NOW 邻居；LoRa 仅回传这些快照。位置、agent 和业务仍使用原来源。`);
    $('loraReports').replaceChildren();for(const item of data.reports){const p=item.report,g=item.gateway_id||r?.node_id||r?.gateway_id,b=html('button',`${label(item.id)} → ${g?label(g):'接收器未提供'} · LoRa RSSI ${Number.isFinite(item.lora?.rssi_dbm)?item.lora.rssi_dbm+' dBm':'未提供'} / SNR ${Number.isFinite(item.lora?.snr_db)?item.lora.snr_db+' dB':'未提供'}`,'loraReport');
      b.append(html('small',`报告 #${p.report_seq} · boot ${p.observer_boot} · PC 收报距今 ${age(item.age)} · 邻居 ${p.neighbors?.length||0}/${p.total_rows??'?'}${p.truncated?'（截断）':''}${p.nd_table_full?' · ND 表曾满':''}`));b.onclick=()=>choose(item.id);$('loraReports').append(b);
    }if(!data.reports.length)text('loraReports',offline?'接收器离线或不可读取；等待恢复，未从 Wi-Fi 补充邻居。':'尚未取得实际 LoRa 帧；等待报告，不用 Wi-Fi 邻居填充。');
  }
  async function refreshLoRa(){
    if(!isLoRa()||window.MobileStudio?.status?.mode==='demo')return;
    const token=++loraVersion,base=$('gateway').value.trim().replace(/\/$/,'');loraLoading=true;
    try{const response=await fetch(base+'/api/v1/lora/topology',{cache:'no-store',signal:AbortSignal.timeout(6000)});if(!response.ok)throw Error('LoRa HTTP '+response.status);const data=await response.json();if(data.schema!=='lora.topology.v1'||!LORA_SOURCES.includes(data.source)||!Array.isArray(data.reports))throw Error('LoRa 来源响应格式不匹配');if(token!==loraVersion)return;loraData=data;loraReadAt=now();loraError='';}
    catch(e){if(token!==loraVersion)return;loraError=e.message;}finally{if(token===loraVersion){loraLoading=false;if(isLoRa())render();}}
  }
  function renderLoRaEdge(edge,detailOpen){
    const i=edge.loraReport,p=i.report,r=edge.raw,detail=$('edgeDetail');
    detail.append(html('strong',`${label(edge.from)} → ${label(edge.to)} · ${sampleState(edge.state)}`));
    detail.append(html('p',`Wi-Fi 发送方 ${edge.from}\nWi-Fi 接收报告者 ${edge.to}\nWi-Fi RSSI：${edge.rssi===null?'未提供':edge.rssi+' dBm'}\n源板采样时最近听到：${age(r.seen_age_ms)}${r.seen_age_ms>=12000?'（裁顶下界）':''}\n源板采样时 ACK 年龄：${age(r.ack_age_ms)}${r.ack_age_ms>=9000?'（裁顶下界）':''}\n源板采样时 RF 帧年龄：${age(r.rf_age_ms)}${r.rf_age_ms>=12000?'（裁顶下界）':''}\n源板本地采样钟：${p.snapshot_at_ms} ms\n报告 boot ${p.observer_boot} / seq ${p.report_seq}；对端 boot ${r.peer_boot}\n上报周期 ${age(p.report_period_ms)} · 本板发前延迟 ${age(p.tx_delay_ms)}`));
    detail.append(html('p',`LoRa 回传 ${label(i.id)} → ${label(i.gateway_id)}\nLoRa 接收 RSSI：${Number.isFinite(i.lora?.rssi_dbm)?i.lora.rssi_dbm+' dBm':'未提供'} / SNR：${Number.isFinite(i.lora?.snr_db)?i.lora.snr_db+' dB':'未提供'}\n网关 boot ${i.gateway_boot} / rx seq ${i.rx_seq}\n网关本地接收钟：${i.received_at_ms} ms\nPC 收报：${i.pc_received_at||'未提供'} · 距今 ${age(i.age)}\n读取会话：${i.reader_session||'未提供'}\n邻居表 ${p.neighbors.length}/${p.total_rows} · ${p.truncated?'已截断':'未截断'}${p.nd_table_full?' · ND 表曾满':''}`));
    detail.append(html('small','这是源板采样当时的状态；不以 LoRa 到达时间续期 Wi-Fi 9 秒互证。源板与网关本地钟不跨机相减。位置、业务收发仍来自原 Wi-Fi 观测。'));
    const raw=document.createElement('details');raw.open=detailOpen;raw.append(html('summary','原始 LoRa 收报与邻居行'),html('pre',JSON.stringify({report:i,neighbor:r},null,2)));detail.append(raw);
  }
  function renderLoRaNodes(){
    const data=lora(),nodes=graphNodes();text('statNodes',nodes.length);text('statLocated',nodes.filter(n=>M.positionState(n,now()).valid).length);text('statOffline','—');
    $('nodeList').replaceChildren();$('unlocated').replaceChildren();
    for(const n of nodes){const node=data.nodes.get(n.id),r=node?.report,pos=M.positionState(n,now()),status=node?.status||(r?'reported':'seen'),b=html('button','','nodeRow'+(selected===n.id?' selected':''));b.style.setProperty('--node-state',status==='reported'?'#8056ad':status==='lost'?'#b3261e':'#aa7021');b.append(html('b',label(n.id)),html('span',status==='reported'?'LoRa 在线':status==='lost'?'采样已失效':'仅被邻居看到','pill'+(status==='reported'?'':status==='lost'?' off':' warn')),html('small',n.id),html('small',r?`LoRa 报告 #${r.report.report_seq} · PC 收报距今 ${age(r.age)}`:'仅出现在 LoRa 邻居快照中'),html('small',`位置另取原来源：${pos.valid?source(n.position?.source):pos.reason}`));b.onclick=()=>choose(n.id);$('nodeList').append(b);if(!pos.valid)$('unlocated').append(html('div',label(n.id)+' · '+pos.reason));}
    if(!nodes.length)text('nodeList','尚无实际 LoRa 成员报告');if(!$('unlocated').children.length)text('unlocated',nodes.length?'成员沿用已有定位来源':'暂无 LoRa 成员');
    if(selected&&data.nodes.has(selected)){const r=data.nodes.get(selected).report,n=model.nodes.get(selected);text('detailTitle',label(selected)+' · LoRa 观测');text('detail',r?`报告者 ${selected}\nboot ${r.report.observer_boot} / report seq ${r.report.report_seq}\n源板采样钟 ${r.report.snapshot_at_ms} ms\nPC 收报 ${r.pc_received_at||'未提供'}\nPC 收报距今 ${age(r.age)}\n位置：${n?source(n.position?.source):'无原位置来源，使用非地理拓扑'}\n邻居快照 ${r.report.neighbors.length}/${r.report.total_rows}${r.report.truncated?'，已截断':''}`:`${selected}\n该成员仅见于其他报告者的邻居行，未收到它自己的 LoRa 报告。\n位置：${n?source(n.position?.source):'无原位置来源，使用非地理拓扑'}`);}
  }
  function reset(){sourceViews.clear();shownSource=$('topologySource').value;loraVersion++;loraData=null;loraError='';loraLoading=false;clearTimeout(radioExpiry);radioExpiry=null;model=M.create();origin=null;view=null;zoom=1;autoFit=true;logical=new Map();layoutKey='';cursor=0;selected='';selectedPacket='';selectedEdge='';packetLog=S.createPacketLog();timelineTruncated=false;animated.clear();pendingAnimation=[];snapshotLoaded=false;snapshotError='';}
  function renderHealth(){
    const studio=window.MobileStudio;
    health=S.fieldHealth({studio:studio?.status,controller:studio?.controller,upstream:studio?.upstream,nodeCount:model.nodes.size,edgeCount:M.edges(model,now()).filter(e=>e.hasObservation!==false).length,snapshotLoaded,snapshotError,external:!!$('gateway').value.trim()});
    text('fieldHealthTitle',(isLoRa()?'Wi-Fi / 业务来源：':'')+health.title);text('fieldHealthNext',health.next);$('fieldHealth').dataset.state=health.state;$('fieldHealth').classList.toggle('warning',health.warning);
    document.querySelector('.workspace').classList.toggle('staleSnapshot',!isLoRa()&&health.warning&&snapshotLoaded);
    if(!model.nodes.size)text('emptyMap',health.title);
  }
  function choose(id){selected=id;render();}
  const edgeAge=e=>Number.isFinite(e.age)?age(e.age):Number.isFinite(e.ageUpperBound)?(Number.isFinite(e.ageLowerBound)?'≥ '+age(e.ageLowerBound)+'，':'')+'≤ '+age(e.ageUpperBound)+'（上界）':Number.isFinite(e.ageLowerBound)?'≥ '+age(e.ageLowerBound)+'（仅下界）':'未知';
  const edgeKey=e=>e.from+'/'+e.to;
  function chooseEdge(e){selectedEdge=edgeKey(e);selected=e.to;render();}
  function bounds(points){if(!points.length)return{x:-300,y:-200,w:600,h:400};const xs=points.map(p=>p.x),ys=points.map(p=>p.y),w=Math.max(160,Math.max(...xs)-Math.min(...xs)),h=Math.max(120,Math.max(...ys)-Math.min(...ys));return{x:(Math.max(...xs)+Math.min(...xs))/2-w*.75,y:(Math.max(...ys)+Math.min(...ys))/2-h*.8,w:w*1.5,h:h*1.6};}
  function geometry(edges){
    const nodes=graphNodes(),located=nodes.filter(n=>M.positionState(n,now()).valid),choice=$('layoutMode').value;
    const next=choice==='topology'||choice==='auto'&&(!nodes.length||located.length!==nodes.length)||isLoRa()&&located.length!==nodes.length;
    if(next!==topology){topology=next;view=null;zoom=1;autoFit=true;}
    const world=new Map();
    if(topology){
      const ids=[...nodes.map(n=>n.id),...edges.flatMap(e=>[e.from,e.to])];
      const key=[...new Set(ids)].sort().join(',')+'|'+edges.map(e=>e.from+e.to+e.state).sort().join(',');
      if(key!==layoutKey){logical=S.topology(ids,edges,logical);layoutKey=key;}
      for(const [id,p]of logical)world.set(id,p);
    }else{
      if(!origin&&located.length)origin={lat:located.reduce((s,n)=>s+n.position.lat,0)/located.length,lon:located.reduce((s,n)=>s+n.position.lon,0)/located.length};
      if(origin)for(const n of located)world.set(n.id,M.project(n.position,origin));
    }
    if(!view||autoFit)view=bounds([...world.values()]);const s=Math.min(850/view.w,450/view.h)*zoom,cx=view.x+view.w/2,cy=view.y+view.h/2;
    const screen=p=>({x:480+(p.x-cx)*s,y:280-(p.y-cy)*s});
    positions=new Map([...world].map(([id,p])=>[id,screen(p)]));
    return{s,cx,cy,screen,world:p=>({x:cx+(p.x-480)/s,y:cy-(p.y-280)/s})};
  }
  let tileKey='';
  function drawTiles(g){
    const on=$('tiles').checked&&!topology&&origin;$('attribution').classList.toggle('hidden',!on);
    if(!on){$('tileLayer').replaceChildren();tileKey='';return;}
    const sw=M.unproject(g.world({x:0,y:580}),origin),ne=M.unproject(g.world({x:960,y:0}),origin);
    let z=18;const tile=(p,z)=>({x:(p.lon+180)/360*2**z,y:(1-Math.asinh(Math.tan(p.lat*Math.PI/180))/Math.PI)/2*2**z});let a,b;
    do{a=tile(ne,z);b=tile(sw,z);if((Math.floor(a.x)-Math.floor(b.x)+1)*(Math.floor(b.y)-Math.floor(a.y)+1)<=25)break;z--;}while(z>1);
    const key=[z,Math.floor(b.x),Math.floor(a.x),Math.floor(a.y),Math.floor(b.y),g.s,g.cx,g.cy].join('/');if(key===tileKey)return;tileKey=key;$('tileLayer').replaceChildren();
    const point=(x,y)=>({lon:x/2**z*360-180,lat:Math.atan(Math.sinh(Math.PI*(1-2*y/2**z)))*180/Math.PI});
    for(let x=Math.floor(b.x);x<=Math.floor(a.x);x++)for(let y=Math.floor(a.y);y<=Math.floor(b.y);y++){
      const p=g.screen(M.project(point(x,y),origin)),q=g.screen(M.project(point(x+1,y+1),origin));
      const img=svg('image',{x:p.x,y:p.y,width:q.x-p.x,height:q.y-p.y,href:`https://tile.openstreetmap.org/${z}/${x}/${y}.png`});img.addEventListener('error',()=>text('notice','联网底图不可用；本地观测仍可用。'));$('tileLayer').append(img);
    }
  }
  function line(layer,from,to,color,dashed=false,width=2){
    const a=positions.get(from),b=positions.get(to);if(!a||!b)return null;const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy);if(d<1)return null;
    const x1=a.x+dx/d*27-dy/d*4,y1=a.y+dy/d*27+dx/d*4,x2=b.x-dx/d*29-dy/d*4,y2=b.y-dy/d*29+dx/d*4;
    const el=svg('line',{x1,y1,x2,y2,stroke:color,'stroke-width':width,'stroke-dasharray':dashed?'6 5':'','marker-end':'url(#arrow)'});layer.append(el);return el;
  }
  function drawPacket(replay=false){
    const layer=$('packetLayer');layer.replaceChildren();const row=packetRows.find(p=>p.key===selectedPacket);if(!row)return;
    if($('packetOverlay').checked){
      for(const route of row.routes.slice(-1))for(let i=1;i<route.path.length;i++){const el=line(layer,route.path[i-1],route.path[i],colors.purple,true,3);if(el)el.append(svg('title',{},'所选业务包选路向量；不是无线邻居线或沿途实收证据'));}
      for(const s of row.segments){const el=line(layer,s.from,s.to,colors.blue,false,3.5);if(el)el.append(svg('title',{},`所选业务包 · ${M.eventInfo(s.event).name} · ${label(s.from)} → ${label(s.to)}`));}
    }
    const selectedEvents=replay?row.events:pendingAnimation;
    if($('animatePackets').checked&&!document.hidden&&observing){
      const allSegments=packetRows.flatMap(p=>p.segments),moves=allSegments.filter(s=>selectedEvents.includes(s.event)).slice(-12);
      for(const [i,s]of moves.entries()){const a=positions.get(s.from),b=positions.get(s.to);if(!a||!b)continue;const dot=svg('circle',{r:5,fill:colors.blue,class:'packetDot'});dot.append(svg('animateMotion',{path:`M ${a.x} ${a.y} L ${b.x} ${b.y}`,dur:'1.7s',begin:(i*.09)+'s',repeatCount:1,fill:'freeze'}),svg('animate',{attributeName:'opacity',values:'0;1;1;0',dur:'1.7s',begin:(i*.09)+'s',fill:'freeze'}));layer.append(dot);}
      for(const e of selectedEvents.slice(-12)){const p=positions.get(M.clean(e.reporter));if(!p)continue;const ring=svg('circle',{cx:p.x,cy:p.y,r:25,fill:'none',stroke:M.eventInfo(e).destinationEvidence?colors.green:colors.blue,'stroke-width':2});ring.append(svg('animate',{attributeName:'r',from:25,to:45,dur:'1.5s',fill:'freeze'}),svg('animate',{attributeName:'opacity',from:.9,to:0,dur:'1.5s',fill:'freeze'}));layer.append(ring);}
    }
    pendingAnimation=[];
  }
  function renderRadio(edges){
    clearTimeout(radioExpiry);radioExpiry=null;$('linkLayer').replaceChildren();
    const pairs=isLoRa()?L.pairs(edges):S.edgePairs(edges);
    for(const pair of pairs){const a=positions.get(pair.a),b=positions.get(pair.b);if(!a||!b)continue;const shape=S.pairGeometry(a,b);
      const adjacent=!selected||selected===pair.a||selected===pair.b,chosen=pair.directions.some(e=>selectedEdge===edgeKey(e));
      const attrs={...shape.attrs,stroke:pair.color,'stroke-width':chosen?4:adjacent?3:1.8,'stroke-dasharray':pair.dash,'marker-start':pair.ba?'url(#rfArrow)':'none','marker-end':pair.ab?'url(#rfArrow)':'none',opacity:adjacent?pair.state==='stale'?.55:1:.16,class:'mapLink',tabindex:0,role:'button','data-pair':pair.key,'data-directions':pair.directions.map(edgeKey).join(','),'data-pair-state':pair.state,'aria-label':`${label(pair.a)} ${pair.both?'↔':pair.ab?'→':'←'} ${label(pair.b)} · ${pair.label}`};
      const el=svg(shape.tag,attrs),title=pair.directions.map(e=>`${label(e.from)} → ${label(e.to)} · ${edgeAge(e)} · RSSI ${e.rssi===null?'未提供':e.rssi+' dBm'}`).join('\n');el.append(svg('title',{},pair.label+'\n'+title));el.onclick=()=>chooseEdge(pair.ab||pair.ba);el.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();chooseEdge(pair.ab||pair.ba);}};$('linkLayer').append(el);
      if(adjacent){const name=pair.both?`${label(pair.a)}↔${label(pair.b)}`:pair.ab?`${label(pair.a)}→${label(pair.b)}`:`${label(pair.b)}→${label(pair.a)}`;$('linkLayer').append(svg('text',{x:shape.label.x,y:shape.label.y-3,'text-anchor':'middle','font-size':chosen?12:10,fill:pair.color,class:'edgeAgeLabel'},name+' · '+pair.label));}
    }
    renderDirections(edges);
    const incoming=edges.filter(e=>e.to===selected),outgoing=edges.filter(e=>e.from===selected);
    if(!selected)text('neighborRelations','选中节点，突出相邻边，并查看“收到谁 / 谁收到我”');
    else{
      const box=$('neighborRelations');box.replaceChildren();
      const line=(caption,list,pick)=>{
        const row=html('div','','relationLine');row.append(html('span',caption,'relationCaption'));
        if(!list.length)row.append(html('small','尚无该方向样本'));
        for(const e of list){const info=radioInfo(e),chip=html('span','','relationChip'),dot=html('i','','relationDot');
          dot.style.background=info.color||'#8d9a9e';chip.append(dot,html('span',label(pick(e))));chip.title=`${label(e.from)} → ${label(e.to)} · ${info.label}`;row.append(chip);}
        box.append(row);
      };
      line('收到谁',incoming,e=>e.from);line('谁收到我',outgoing,e=>e.to);
    }
    const deadlines=[];
    for(const e of edges){const p=e.directEvidence;if(e.mutual&&Number.isFinite(e.mutualRemaining)&&e.mutualRemaining>0)deadlines.push(e.mutualRemaining);if(p?.valid&&Number.isFinite(p.seen_age_upper_bound_ms))deadlines.push((p.seen_limit_ms??12000)-p.seen_age_upper_bound_ms);if(p?.confirmed&&Number.isFinite(p.confirmation_age_upper_bound_ms))deadlines.push((p.confirmation_limit_ms??9000)-p.confirmation_age_upper_bound_ms);}
    const next=deadlines.filter(ms=>ms>0).sort((a,b)=>a-b)[0];
    if(!isLoRa()&&Number.isFinite(next)&&observing&&!document.hidden)radioExpiry=setTimeout(()=>{radioExpiry=null;if(observing&&!document.hidden)renderRadio(radioEdges());},Math.max(1,Math.ceil(next)+1));
    return pairs;
  }
  function renderMap(edges){
    const g=geometry(edges),current=now();for(const id of ['gridLayer','linkLayer','nodeLayer','scaleLayer'])$(id).replaceChildren();
    drawTiles(g);const step=[10,20,50,100,200,500,1000,5000,10000].find(v=>v*g.s>=70)||50000;
    if(!topology){const min=g.world({x:0,y:580}),max=g.world({x:960,y:0});for(let x=Math.ceil(min.x/step)*step;x<=max.x;x+=step){const p=g.screen({x,y:0});$('gridLayer').append(svg('line',{x1:p.x,y1:0,x2:p.x,y2:580,stroke:'#cbdcdb','stroke-width':.7}));}for(let y=Math.ceil(min.y/step)*step;y<=max.y;y+=step){const p=g.screen({x:0,y});$('gridLayer').append(svg('line',{x1:0,y1:p.y,x2:960,y2:p.y,stroke:'#cbdcdb','stroke-width':.7}));}}
    const pairs=renderRadio(edges);
    for(const [id,p]of positions){const n=model.nodes.get(id),lr=isLoRa()?lora().nodes.get(id):null,active=isLoRa()?!!lr?.report:n&&M.online(n,current),group=svg('g',{class:'mapNode',tabindex:0,role:'button','data-node':id,'aria-label':`${label(id)} · ${isLoRa()?lr?.report?'LoRa 来源报告':'LoRa 快照邻居':n?active?'报告在线':'报告失联':'仅邻居观测'} · ${topology?'非地理拓扑位置':source(n?.position?.source)}`});
      const nodeState=isLoRa()?(lr?.status||(lr?.report?'reported':'seen')):null;
      const ringColor=isLoRa()?(nodeState==='reported'?'#8056ad':nodeState==='lost'?'#b3261e':'#aa7021'):(active?'#1c8270':'#8d9a9e');
      group.append(svg('circle',{cx:p.x,cy:p.y,r:25,fill:active?'#fff':nodeState==='lost'?'#fdeceb':'#e6ebea',stroke:selected===id?'#153e46':ringColor,'stroke-width':selected===id?4:2}),svg('text',{x:p.x,y:p.y+5,'text-anchor':'middle','font-size':label(id).length>5?12:17,'font-weight':700,fill:active?'#1a655b':'#7c8b90'},label(id)));
      group.append(svg('text',{x:p.x,y:p.y+43,'text-anchor':'middle','font-size':11,fill:'#536e74'},isLoRa()?lr?.report?'LoRa #'+lr.report.report.report_seq+' · '+age(lr.report.age):'仅邻居快照':n?topology?M.online(n,current)?'报告在线':'报告失联':source(n.position?.source)+' · '+age(M.positionState(n,current).age):'仅邻居被观测'));
      const recent=[...model.events].reverse().find(e=>M.clean(e.reporter)===id&&['tx_submit','rx_relay','rx_local'].includes(e.event)&&Number.isFinite(e.received_ms)&&Math.max(0,(model.server?.now_ms??e.received_ms)-e.received_ms)<12000);if(recent)group.append(svg('text',{x:p.x,y:p.y-37,'text-anchor':'middle','font-size':12,'font-weight':700,fill:recent.event==='rx_local'?colors.green:colors.blue},({tx_submit:'TX 提交',rx_relay:'RELAY 收',rx_local:'RX 收到'})[recent.event]));
      const agent=n?.agent;if(active&&agent?.running===true)group.append(svg('circle',{cx:p.x+19,cy:p.y-18,r:5,fill:'#20a985'}));
      if(window.MobileStudio?.status?.mode==='live'&&window.MobileStudio?.pc?.entries?.some(e=>M.clean(e.node_id)===id&&e.connected===true))group.append(svg('text',{x:p.x,y:p.y+59,'text-anchor':'middle','font-size':10,fill:'#326eac'},'热点 IP 入口'));
      group.onclick=()=>choose(id);group.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(id);}};$('nodeLayer').append(group);
    }
    $('emptyMap').classList.toggle('hidden',positions.size>0);text('emptyMap',isLoRa()&&!positions.size?loraError?'LoRa 来源不可读取':'等待实际 LoRa 邻居报告':!model.nodes.size?health?.title||'等待节点报告':topology?'尚无节点报告 · 等待接入':'尚无有效 GPS · 可切换动态拓扑查看节点');
    text('mapScope',(isLoRa()?'LoRa 回传快照 · ':'Wi-Fi 即时观测 · ')+(topology?isLoRa()&&graphNodes().some(n=>!M.positionState(n,current).valid)?'动态关系布局 · 缺定位成员已回退，非地理位置':'动态关系布局 · 非地理位置，无距离含义':origin?`GPS 等米制投影 · 网格 ${step} m`:'等待有效 GPS')+` · ${edges.length} 个实际方向合为 ${pairs.length} 对连线 · 点节点突出相邻边`);
    if(!topology&&origin){const metres=[1,5,10,20,50,100,200,500,1000,5000,10000].filter(v=>v*g.s<=150).at(-1)||1,len=metres*g.s;$('scaleLayer').append(svg('path',{d:`M 36 537 V 545 H ${36+len} V 537`,stroke:'#284c50','stroke-width':2,fill:'none'}),svg('text',{x:36,y:563,'font-size':11,fill:'#284c50'},metres+' m'));}
    drawPacket();
  }
  function renderAgents(nodes){
    const pc=window.MobileStudio?.pc,entries=pc?.entries||[],demo=window.MobileStudio?.status?.mode==='demo';
    text('entrySummary',demo?'软件演示隔离运行；无实板热点或 RF 测量':pc?`PC ${pc.pc_address||pc.pc_id||'身份未提供'} · 当前有效 IP 入口 ${entries.filter(e=>e.connected===true).map(e=>label(e.node_id)).join('、')||'无'}。热点连接不等于板间 RF 邻居。`:'热点入口状态尚未读取；不推测连接状态');
    $('agents').replaceChildren();for(const n of nodes){const a=n.agent||{},card=html('article','','agentCard'),counts=a.counters||n.counts||{};
      card.append(html('strong',n.label||n.id),html('span',typeof a.running==='boolean'?a.running?'运行中':'已停止':'未报告运行状态','agentState'+(a.running===true?' running':'')));
      card.append(html('small',`来源：${source(a.source)} · ${M.online(n,now())?'报告在线':'报告已失联，状态为上次记录'}`));
      if(Object.keys(counts).length)card.append(html('p',`源接纳 ${counts.source_admitted??'—'} · 源提交 ${counts.source_submitted??'—'} · 目的收件 ${counts.destination_received??'—'}\n中继接收 ${counts.relay_received??'—'} · 中继提交 ${counts.relay_submitted??'—'}`));
      else{const events=model.events.filter(e=>M.clean(e.reporter)===n.id),count=kind=>events.filter(e=>e.event===kind).length;card.append(html('p',`本页观测：TX 提交 ${count('tx_submit')} · RX 本地 ${count('rx_local')} · 中继收 ${count('rx_relay')}\n仅保留最近最多1000条事件，非累计交付率`));}
      if(a.record_overwritten!==undefined||a.sampled_records_skipped!==undefined)card.append(html('small',`RAM 覆盖 ${a.record_overwritten??'未知'} · 本轮抽样跳过 ${a.sampled_records_skipped??'未知'}，不据此计算交付率`));
      $('agents').append(card);
    }if(!nodes.length)text('agents','尚无节点报告；不会预填 agent 或收发统计');
  }
  function renderPackets(){
    packetRows=S.mergePackets(packetLog,model.events,M.eventInfo,{nodes:[...model.nodes.values()],timelineTruncated,pinnedKey:$('followPackets').checked?null:selectedPacket});if(!packetRows.some(p=>p.key===selectedPacket))selectedPacket=packetRows[0]?.key||'';
    const filter=$('packetStateFilter').value,visible=packetRows.filter(p=>filter==='all'||p.state===filter),counts={};for(const p of packetRows)counts[p.state]=(counts[p.state]||0)+1;
    text('packetSummary',`本页保留 ${packetRows.length} / 128 包 · 排队 ${counts.queued||0} · 待收件 ${counts.awaiting_receipt||0} · 实收 ${counts.destination_received||0} · 无路/拒绝 ${(counts.no_route||0)+(counts.rejected||0)} · 未知 ${counts.delivery_unknown||0}`);
    const gaps=[...model.nodes.values()].some(n=>n.agent?.record_overwritten>0||n.agent?.sampled_records_skipped>0||n.events_dropped>0)||timelineTruncated;
    text('packetCoverage',gaps?'观测含 RAM 覆盖、抽样跳过或时间线保留限制；没有目的收件记录不能直接判为丢包。目的原字节匹配后会自动更新同一包。':'状态只依据已收到的原事件；排队、提交和链路回调都不等于目的实收，异步收件按完整原身份合并。');
    $('packetList').replaceChildren();for(const p of visible.slice(0,24)){const b=html('button','',`packetRow${p.key===selectedPacket?' selected':''}`),color=p.state==='destination_received'?'green':['no_route','rejected','payload_conflict'].includes(p.state)?'red':p.state==='awaiting_receipt'?'blue':'gray';
      b.append(html('b',`${label(p.origin)} → ${label(p.dst)}`),html('span',p.stateLabel,color),html('small',`boot ${p.origin_boot} · seq ${p.seq} · ${p.payloads.length?p.payloads[0].length/2:'未知'} 字节 · ${p.segments.length} 条本跳观测`));
      b.onclick=()=>{selectedPacket=p.key;$('followPackets').checked=false;render();};$('packetList').append(b);
    }if(!visible.length)text('packetList',packetRows.length?'当前筛选下没有记录':'尚无带完整身份的业务包');
    const p=packetRows.find(p=>p.key===selectedPacket);$('replayPacket').disabled=!p;$('packetDetail').replaceChildren();if(!p){text('packetDetail','选择业务包，核对身份、载荷和实际观测跳；动画不表示无线时延。');return;}
    const detail=$('packetDetail');detail.append(html('strong',`${label(p.origin)} → ${label(p.dst)} · ${p.stateLabel}`),html('code',p.key),html('p',p.reason));
    if(p.last)detail.append(html('p',`最后观测：${label(p.last.reporter)} · ${M.eventInfo(p.last).name} · ${Number.isFinite(p.last.received_ms)?'网关收报 '+new Date(p.last.received_ms).toLocaleTimeString('zh-CN'):'未提供网关收报时间'}`));
    if(p.coverageNotes.length)detail.append(html('p','观察限制：'+p.coverageNotes.join('；')+'。不能据缺失收件判为丢包；已见目的原字节的证据仍有效。','coverageWarning'));
    for(const bytes of p.payloads){detail.append(html('p',S.payload(bytes)===null?'二进制载荷（非有效 UTF-8）':'文本：'+S.payload(bytes)),html('code','原始 HEX：'+bytes));}
    if(!p.payloads.length)detail.append(html('p','本次观察未提供载荷原字节'));
    for(const route of p.routes.slice(-1))detail.append(html('p','选路向量（紫色虚线）：'+route.path.map(label).join(' → ')+'；不是沿途实收证明'));
    detail.append(html('p',p.segments.length?'实际本跳观测（蓝色）：'+p.segments.map(s=>`${label(s.from)} → ${label(s.to)} [${M.eventInfo(s.event).name}]`).join('；'):'当前没有可定位的逐跳字段；不从端点或选路向量补全路径'));
    const observations=html('ol','','packetObservations');for(const e of p.events.slice(-8))observations.append(html('li',`${label(e.reporter)} · ${M.eventInfo(e).name}${Number.isFinite(e.received_ms)?' · 网关 '+new Date(e.received_ms).toLocaleTimeString('zh-CN'):''}`));detail.append(observations);
    detail.append(html('small','来源：'+[...new Set(p.events.map(e=>e.evidence_source||e.transport_source||e.rf_source||'网关原始事件'))].join('、')+'。重看仅播放已保存的观测，不发送包。'));
  }
  function renderTimeline(){
    const filter=$('eventFilter').value;$('timeline').replaceChildren();
    for(const e of [...model.events].reverse().filter(e=>filter==='all'||M.eventInfo(e).group===filter&&(filter!=='network'||e.event!=='report')).slice(0,300)){const info=M.eventInfo(e);const row=html('div','','event'),t=e.at_ms??e.elapsed_ms??e.timestamp_ms;
      row.append(html('time',typeof t==='number'?(t/1000).toFixed(1)+' s':Number.isFinite(e.received_ms)?new Date(e.received_ms).toLocaleTimeString('zh-CN'):'时间未提供'),html('b',info.name,info.color));
      const body=html('div',`${label(e.reporter)}${e.peer_id?' · 对方 '+label(e.peer_id):''}${Array.isArray(e.path)?' · '+e.path.map(label).join(' → '):''}`);
      if(e.origin)body.append(html('code',` ${info.group==='route'||e.sequence_scope==='route_request'?'寻路请求身份':'业务身份'} ${e.origin}/${e.origin_boot??e.boot??'?'}/${e.seq??'?'} → ${e.dst||'?'}${e.payload_hex!==undefined?' · 原字节 '+e.payload_hex:''}`));row.append(body);$('timeline').append(row);
    }if(!$('timeline').children.length)text('timeline','当前筛选下尚无事件');
  }
  function renderDirections(edges){
    $('directions').replaceChildren();for(const e of edges){const row=document.createElement('tr'),cell=document.createElement('td'),button=html('button',`${label(e.from)} → ${label(e.to)}`,'directionButton'),info=radioInfo(e);button.onclick=()=>chooseEdge(e);cell.append(button);row.append(cell);for(const value of [e.rssi===null?'':e.rssi+' dBm',edgeAge(e),info.label,isLoRa()?'采样时状态，不判当前互证':e.mutual?'新鲜双向互证':'未有新鲜互证',source(e.rf_source)])row.append(html('td',value));$('directions').append(row);}if(!edges.length){const tr=document.createElement('tr'),td=html('td','尚无板间邻居样本；热点/IP 注册和业务端点不当作 RF 直边');td.colSpan=6;tr.append(td);$('directions').append(tr);}
    const detailOpen=$('edgeDetail').querySelector('details')?.open===true,edge=edges.find(e=>edgeKey(e)===selectedEdge);$('edgeDetail').replaceChildren();
    if(edge?.loraReport){renderLoRaEdge(edge,detailOpen);return;}
    if(edge){
      const info=S.edgeInfo(edge),p=edge.directEvidence;$('edgeDetail').append(html('strong',`${label(edge.from)} → ${label(edge.to)} · ${info.label}`));
      $('edgeDetail').append(html('p',`发送方 ${edge.from}\n接收报告者 ${edge.to}\n连接证据年龄：${edgeAge(edge)}\n连接新鲜度：${edge.sampleFreshness}\n互证：${edge.mutual?'网关确认双方即时证据当前有效':'无当前双向互证，不能补另一方向'}`));
      if(p)$('edgeDetail').append(html('p',`即时邻居快照：匹配本次查询和双方启动身份\n观察者 boot：${p.observer_boot}\n样本所带对端 boot：${p.peer_boot??'未提供'}\n最近听到年龄界限：${Number.isFinite(p.seen_age_upper_bound_ms)?'≤ '+age(p.seen_age_upper_bound_ms):Number.isFinite(p.seen_age_lower_bound_ms)?'≥ '+age(p.seen_age_lower_bound_ms):'未知'} / 限制 ${age(p.seen_limit_ms??12000)}\n双向确认年龄界限：${Number.isFinite(p.confirmation_age_upper_bound_ms)?'≤ '+age(p.confirmation_age_upper_bound_ms):Number.isFinite(p.confirmation_age_lower_bound_ms)?'≥ '+age(p.confirmation_age_lower_bound_ms):'未知'} / 限制 ${age(p.confirmation_limit_ms??9000)}\n本向有效：${p.valid?'是':'否'}；本向确认：${p.confirmed?'是':'否'}；启动身份校验：${p.epoch_verified?'通过':'未通过'}\n查询 RTT 上界：${age(p.rtt_upper_bound_ms)}\n即时查询收报：${Number.isFinite(p.received_ms)?new Date(p.received_ms).toLocaleTimeString('zh-CN'):'未提供'}`));
      else $('edgeDetail').append(html('p',`观察者 boot：${edge.raw.observer_boot??'未提供'}\n样本所带对端 boot：${edge.raw.peer_boot??'未提供'}\n样本报告序号：${edge.raw.sample_report_seq??'未提供'}\n样本报告锚点：${Number.isFinite(edge.raw.sample_received_ms)?new Date(edge.raw.sample_received_ms).toLocaleTimeString('zh-CN'):'未提供'}`));
      const rssiAge=Number.isFinite(edge.rssiAge)?age(edge.rssiAge):Number.isFinite(edge.rssiUpperBound)?(Number.isFinite(edge.rssiLowerBound)?'≥ '+age(edge.rssiLowerBound)+'，':'')+'≤ '+age(edge.rssiUpperBound)+'（上界）':Number.isFinite(edge.rssiLowerBound)?'≥ '+age(edge.rssiLowerBound)+'（仅下界）':'未知';
      $('edgeDetail').append(html('p',`接收 RSSI：${edge.rssi===null?'':edge.rssi+' dBm'}\nRSSI 来源：${source(edge.rf_source)}\nRSSI 独立样本年龄：${rssiAge}\nRSSI 旧样本失效原因：${edge.raw.invalidated_reason??'无明示'}`));
      if(p){$('edgeDetail').append(html('small','连接时效来自即时查询；RSSI 采用它自己的 RF 帧年龄，不借连接确认刷新。'));if(Number.isFinite(edge.mutualRemaining))$('edgeDetail').append(html('p','本次互证剩余有效期：'+age(edge.mutualRemaining)));if(p.nd_full>0)$('edgeDetail').append(html('p','ND 表累计容量拒绝 '+p.nd_full+'；邻居观测受表容量限制。'));}
      if(edge.rssi===null)$('edgeDetail').append(html('small','原报告没有提供 RSSI，数值留空。'));
      const reverse=edges.find(e=>e.from===edge.to&&e.to===edge.from);if(reverse)$('edgeDetail').append(html('p',`反向独立样本 ${label(reverse.from)} → ${label(reverse.to)}：${radioInfo(reverse).label}；连接年龄 ${edgeAge(reverse)}；RSSI ${reverse.rssi===null?'':reverse.rssi+' dBm'}。失效方向不与仍有效方向共用箭头。`));
      const raw=document.createElement('details');raw.open=detailOpen;raw.append(html('summary','原始方向记录'),html('pre',JSON.stringify(edge.raw,null,2)));$('edgeDetail').append(raw);
    }else text('edgeDetail',selectedEdge?'该方向未列在当前快照，不能据此补造关系；请选择现有样本。':'点击图上的箭头或表格方向，查看实际 RSSI、年龄、观察者和互证依据。');
  }
  function render(){
    renderHealth();renderLoRa();
    const nodes=[...model.nodes.values()],current=now(),edges=radioEdges();text('statNodes',nodes.length);text('statLocated',nodes.filter(n=>M.positionState(n,current).valid).length);text('statLinks',edges.length);text('statOffline',nodes.filter(n=>!M.online(n,current)).length);
    $('nodeList').replaceChildren();$('unlocated').replaceChildren();for(const n of nodes){const active=M.online(n,current),pos=M.positionState(n,current),b=html('button','',`nodeRow${selected===n.id?' selected':''}`);b.append(html('b',n.label||n.id),html('span',active?'报告在线':'报告失联','pill'+(active?'':' off')),html('small',n.id),html('small',`GPS ${source(n.position?.source)} · ${pos.valid?age(pos.age):pos.reason} · 报告 ${age(M.reportAge(n,current))}`));b.onclick=()=>choose(n.id);$('nodeList').append(b);if(!pos.valid)$('unlocated').append(html('div',`${n.label||n.id} · ${pos.reason}`));}
    if(!nodes.length)text('nodeList','尚无实际节点报告');if(!$('unlocated').children.length)text('unlocated',nodes.length?'全部已定位':'暂无节点');
    const n=model.nodes.get(selected);text('detailTitle',n?(n.label||n.id)+' · 来源与状态':'选择节点查看来源');text('detail',n?`${n.id}\nboot ${n.boot_id} · 报告实例 ${n.session_id}\nGPS ${source(n.position?.source)} · ${M.positionState(n,current).reason||age(M.positionState(n,current).age)}\n${n.position?'经纬度 '+n.position.lat+', '+n.position.lon+'\n':''}报告年龄 ${age(M.reportAge(n,current))}\n节点来源 ${n.source||'网关节点报告'}\n无线来源 ${[...new Set(edges.filter(e=>e.to===n.id).map(e=>source(e.rf_source)))].join('、')||'尚无邻居样本'}`:'节点、定位、agent 和无线链路各自保留来源；不从热点客户端关系生成 RF 边');
    const incoming=edges.filter(e=>e.to===selected),outgoing=edges.filter(e=>e.from===selected);
    if(!selected)text('neighborRelations','选中节点，突出相邻边，并查看“收到谁 / 谁收到我”');
    else{
      const box=$('neighborRelations');box.replaceChildren();
      const line=(caption,list,pick)=>{
        const row=html('div','','relationLine');row.append(html('span',caption,'relationCaption'));
        if(!list.length)row.append(html('small','尚无该方向样本'));
        for(const e of list){const info=radioInfo(e),chip=html('span','','relationChip'),dot=html('i','','relationDot');
          dot.style.background=info.color||'#8d9a9e';chip.append(dot,html('span',label(pick(e))));chip.title=`${label(e.from)} → ${label(e.to)} · ${info.label}`;row.append(chip);}
        box.append(row);
      };
      line('收到谁',incoming,e=>e.from);line('谁收到我',outgoing,e=>e.to);
    }
    if(isLoRa())renderLoRaNodes();
    text('sampleAgeTitle',isLoRa()?'源板采样时听到年龄':'连接证据年龄');
    renderAgents(nodes);renderPackets();renderTimeline();renderMap(edges);
  }
  async function refresh(){
    const token=++version;try{
      await window.MobileStudio?.refresh();if(token!==version)return;
      const base=$('gateway').value.trim().replace(/\/$/,'');if(base&&!/^https?:\/\//i.test(base))throw Error('网关地址需为 http 或 https');
      if(baseKey!==base){reset();baseKey=base;instance=null;}
      const get=async path=>{const response=await fetch(base+path,{cache:'no-store',signal:AbortSignal.timeout(6000)});if(!response.ok)throw Error(path+' HTTP '+response.status);return response.json();};
      const [state,initial]=await Promise.all([get('/api/v1/state'),get('/api/v1/timeline?after='+cursor)]);if(token!==version)return;
      let history=initial;if(instance!==null&&state.gateway_instance!==instance){reset();history=await get('/api/v1/timeline?after=0');if(token!==version)return;}
      if(history.gateway_instance!==state.gateway_instance)throw Error('网关会话在读取中变化，等待同一实例');
      instance=state.gateway_instance;cursor=history.cursor??cursor;timelineTruncated||=history.truncated===true;M.apply(model,{...state,events:history.events||[]},now());snapshotLoaded=true;snapshotError='';
      const data=model.events.filter(e=>M.eventInfo(e).group==='data'&&!animated.has(e._key));pendingAnimation=data.slice(-16);for(const e of model.events)animated.add(e._key);if(animated.size>4000)animated=new Set(model.events.map(e=>e._key));
      if(data.length&&$('followPackets').checked){const key=S.packetKey(data.at(-1));if(key)selectedPacket=key;}
      const demo=state.view_mode==='demo'||window.MobileStudio?.status?.mode==='demo';text('sourceBadge',demo?'软件演示 · host_model / 模拟 RF':'现场报告 · 来源分别显示');$('sourceBadge').classList.toggle('synthetic',demo);
      const upstreamUnavailable=!base&&window.MobileStudio?.status?.mode==='live'&&window.MobileStudio?.upstream?.state==='unreachable';
      text('connection',(upstreamUnavailable?'页面在线 · 上游未连接':'已读取')+' · '+new Date().toLocaleTimeString('zh-CN'));$('notice').classList.remove('error');
      text('notice',(state.empty_reason?state.empty_reason+'。':'')+(history.truncated?'时间线保留有界，较早记录已截断。':'')+(demo?'演示使用实际软件 agent/GPS 进程与主机模型传输，非实板 RF。':'现场只读观测；模拟 GPS 只改变位置层，不改变 RF 边和板内 agent。')+' 蓝色包段来自本跳原事件；紫色虚线仅为选路向量。');
      render();document.dispatchEvent(new CustomEvent('mobilemapstate',{detail:state}));
    }catch(e){if(token!==version)return;snapshotError=e.message;renderHealth();renderRadio(radioEdges());text('connection','网关未连接');$('notice').classList.add('error');text('notice','读取失败：'+e.message+'。保留上次快照并继续重连；网关断开本身不表示无线节点失联。');}
  }
  async function tick(){if(!observing||document.hidden||inFlight)return;inFlight=true;try{await window.MobileStudio?.ready;if(observing&&!document.hidden)await Promise.all([refresh(),refreshLoRa()]);}finally{inFlight=false;}if(observing&&!document.hidden)timer=setTimeout(tick,2000);}
  function pause(){observing=false;version++;loraVersion++;clearTimeout(radioExpiry);radioExpiry=null;clearTimeout(timer);timer=null;$('live').classList.remove('on');text('live','继续现场观测');text('connection','已暂停，保留上次观测');$('map').pauseAnimations?.();}
  function start(){observing=true;renderRadio(radioEdges());$('live').classList.add('on');text('live','暂停现场观测');$('map').unpauseAnimations?.();tick();}
  $('refresh').onclick=()=>{if(!inFlight)Promise.all([refresh(),refreshLoRa()]);};$('live').onclick=()=>observing?pause():start();
  $('topologySource').onchange=()=>{if(window.MobileStudio?.status?.mode==='demo')$('topologySource').value='wifi';
    sourceViews.set(shownSource,{origin,view,zoom,autoFit,logical,layoutKey,selectedEdge,selected,topology});shownSource=$('topologySource').value;const saved=sourceViews.get(shownSource);
    origin=saved?.origin||null;view=saved?.view||null;zoom=saved?.zoom||1;autoFit=saved?.autoFit??true;logical=saved?.logical||new Map();layoutKey=saved?.layoutKey||'';selectedEdge=saved?.selectedEdge||'';selected=saved?.selected||'';topology=saved?.topology??true;
    loraVersion++;render();if(observing&&!document.hidden)refreshLoRa();};
  $('layoutMode').onchange=()=>{view=null;autoFit=true;zoom=1;render();};$('fit').onclick=()=>{autoFit=true;view=null;zoom=1;render();};$('zoomIn').onclick=()=>{autoFit=false;zoom=Math.min(8,zoom*1.4);render();};$('zoomOut').onclick=()=>{autoFit=false;zoom=Math.max(.25,zoom/1.4);render();};$('tiles').onchange=render;$('eventFilter').onchange=renderTimeline;$('packetStateFilter').onchange=renderPackets;$('packetOverlay').onchange=()=>drawPacket();
  $('replayPacket').onclick=()=>{const p=packetRows.find(p=>p.key===selectedPacket);if(p){pendingAnimation=p.events;drawPacket(true);}};
  $('gateway').onchange=()=>{loraVersion++;loraData=null;loraError='';version++;clearTimeout(timer);timer=null;if(observing)tick();};
  document.addEventListener('studiohealth',renderHealth);
  // Toggling the GPS layer must redraw at once instead of waiting for the next poll.
  document.addEventListener('studiogps',()=>{version++;loraVersion++;if(!observing||document.hidden)return;Promise.all([refresh(),refreshLoRa()]).catch(()=>{});});
  document.addEventListener('studiochanging',()=>{version++;clearTimeout(timer);timer=null;reset();instance=null;text('sourceBadge','正在切换，等待同一来源报告');render();});
  document.addEventListener('studiochange',()=>{const demo=window.MobileStudio?.status?.mode==='demo',loraOption=$('topologySource').querySelector('option[value="lora"]');if(demo)$('topologySource').value='wifi';if(loraOption)loraOption.disabled=demo;version++;reset();instance=null;clearTimeout(timer);timer=null;render();if(observing&&!document.hidden){if(inFlight)setTimeout(()=>{if(observing&&!document.hidden)tick();},100);else tick();}});
  let drag=null;$('map').addEventListener('pointerdown',e=>{if(e.target.closest('.mapNode,.mapLink'))return;const rect=$('map').getBoundingClientRect(),g=geometry(radioEdges());autoFit=false;drag={x:e.clientX,y:e.clientY,view:{...view},factor:960/rect.width/g.s};$('map').setPointerCapture(e.pointerId);});$('map').addEventListener('pointermove',e=>{if(!drag)return;view={...drag.view,x:drag.view.x-(e.clientX-drag.x)*drag.factor,y:drag.view.y+(e.clientY-drag.y)*drag.factor};render();});$('map').addEventListener('pointerup',()=>drag=null);
  document.addEventListener('visibilitychange',()=>{version++;loraVersion++;clearTimeout(timer);timer=null;if(document.hidden){clearTimeout(radioExpiry);radioExpiry=null;$('map').pauseAnimations?.();text('connection','页面隐藏，读取已暂停');}else if(observing){renderRadio(radioEdges());$('map').unpauseAnimations?.();tick();}});window.addEventListener('pagehide',pause);
  render();start();
})();

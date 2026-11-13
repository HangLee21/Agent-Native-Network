'use strict';
let sendBusy=false,sendVersion=0,edgeMode=false,localMAC=null,messageRun=null,messagePoll=null,edgeCursor=0,uncertain=false;
const sendText=(id,v)=>document.getElementById(id).textContent=v;
function payloadBytes(){if(document.getElementById('hexMode').checked){const hex=document.getElementById('messageHex').value.replace(/\s+/g,'');if(!/^(?:[a-fA-F0-9]{2})*$/.test(hex))throw Error('HEX 必须是成对的十六进制字符。');return Uint8Array.from(hex.match(/../g)||[],h=>parseInt(h,16));}return new TextEncoder().encode(document.getElementById('message').value);}
function payloadHex(){return Array.from(payloadBytes(),b=>b.toString(16).padStart(2,'0')).join('');}
function messageEdit(){sendVersion++;plan=null;document.getElementById('hardwareRun').disabled=true;refreshSend();}
function refreshSend(){let error='',size=0;try{size=payloadBytes().length;if(size>160)error='最多160字节，当前'+size+'字节。';}catch(e){error=e.message;}sendText('byteCount',error||size+' / 160 字节');document.getElementById('byteCount').classList.toggle('error',!!error);const target=edgeMode?window.edgeNeighbors?.selection():null,dst=edgeMode?(target?.name||target?.mac||'未选择设备'):document.getElementById('dst').value;sendText('messageTitle','发送消息 → '+dst);sendText('sendMessage',sendBusy?'发送处理中…':'发送给 '+dst);const invalidRoute=!edgeMode&&draft?.hops===null&&document.getElementById('algorithm').value!=='mid';if(invalidRoute&&!error)sendText('byteCount',size+' / 160 字节 · 请选择1–4跳，或原MID不限跳');document.getElementById('sendMessage').disabled=sendBusy||uncertain||!draft||!!error||invalidRoute||!!window.adhocEntry?.blocked()||(edgeMode?!target?.canSend:draft.src===draft.dst);}
function operation(){document.body.dataset.operation=document.getElementById('operation').value;if(document.body.dataset.operation==='adhoc'){window.joinReplay?.stop();window.adhocEntry?.render();refreshSend();return;}window.adhocEntry?.render();const hw=document.body.dataset.operation==='hardware';for(const o of document.getElementById('algorithm').options)o.hidden=hw?['latency_aware','fixed'].includes(o.value):o.value==='hops';if(hw&&['latency_aware','fixed'].includes(document.getElementById('algorithm').value))document.getElementById('algorithm').value='hops';if(!hw&&document.getElementById('algorithm').value==='hops')document.getElementById('algorithm').value='latency_aware';messageEdit();if(document.body.dataset.operation==='hardware'){actual=[];sendText('graphPath','实板发送以服务反馈为准，图中不绘制候选作实际路径。');draw();}}
function renderInbox(rows){const box=document.getElementById('inbox');box.replaceChildren();if(!rows.length){box.textContent='尚无收件记录。';return;}for(const r of rows){const line=document.createElement('div'),hex=r.payload_hex||'';let message;try{const b=Uint8Array.from(hex.match(/../g)||[],h=>parseInt(h,16));message=new TextDecoder('utf-8',{fatal:true}).decode(b);}catch{message='HEX '+hex;}line.textContent=(r.origin||r.node_id||'?')+' → '+(r.dst||'?')+' · '+(r.origin_boot??'?')+':'+(r.seq??r.packet_seq??'?')+'\n'+message;box.append(line);}}
async function senderStatus(){try{const s=await api('/api/edge/status');edgeMode=s.mode==='single_local_board';localMAC=s.node_id;if(edgeMode){const bindings=s.labels||snapshot?.labels||{},label=Object.keys(bindings).find(k=>String(bindings[k]).toLowerCase()===String(localMAC).toLowerCase());window.senderLocalSource=label||null;if(label&&draft){draft.src=label;document.getElementById('src').value=label;document.getElementById('src').disabled=true;for(const id of ['algorithm','hops','nodeSet'])document.getElementById(id).disabled=true;fields();}sendText('deploymentMode','分机 · 本地 '+(label||localMAC));sendText('physicalStatus','仅访问本机一块板；发送反馈不代表远端收到。');sendText('inboxNote','仅本板 rx_local 收件，不查询远端设备。');document.getElementById('hardwarePlan').disabled=true;document.getElementById('hardwareRun').disabled=true;window.edgeNeighbors?.init(s);}refreshSend();}catch(e){window.adhocEntry?.failure(e.message);if(edgeMode||document.body.dataset.deployment==='local'){edgeMode=true;window.edgeNeighbors?.disconnect(e.message);sendText('deploymentMode','分机 · 本板未连接');sendText('physicalStatus','本板状态读取失败：'+e.message);}else{edgeMode=false;if(document.body.dataset.operation!=='adhoc')sendText('deploymentMode','台架 · 实板 / 仿真');document.body.dataset.deployment='bench';}}finally{window.senderCapabilitiesReady=true;document.dispatchEvent(new Event('capabilitieschange'));}}
async function receiveMessages(){try{if(edgeMode){const r=await api('/api/edge/inbox');edgeCursor=r.cursor??edgeCursor;renderInbox(r.records||[]);}else if(messageRun){await readMessageRun();}else sendText('inboxNote','本次尚未发送；台架收件随当前发送任务反馈显示。');}catch(e){sendText('inboxNote','读取收件失败：'+e.message);}}
async function readMessageRun(){const r=await api('/api/hardware/runs/'+messageRun),j=r.run||r,result=j.result||j;sendText('hardwareRaw',json(r));const packets=j.packets||result.packets||result.summary?.packets||[];const matching=packets.filter(p=>p.destination_received===true);if(matching.length){renderInbox(matching.map(p=>({...p,origin:p.origin||p.identity?.origin||p.identity?.[0],origin_boot:p.origin_boot??p.identity?.origin_boot??p.identity?.[1],seq:p.seq??p.identity?.seq??p.identity?.[2],dst:p.dst||p.identity?.dst||p.identity?.[3]})));sendText('sendFeedback','目的端已收到 '+matching.length+' 包；已按原包身份与载荷匹配。');}else{const state=j.state||result.state||result.status||'执行中';sendText('sendFeedback','实板任务 '+state+'；尚无匹配的目的端收件证据。'+(j.error?'\n'+(j.error.message||j.error):''));}window.routeView?.hardwareRecord(j,true);return {j,r};}
async function trackMessage(deadline){try{const {j}=await readMessageRun();if(['running','queued','stopping'].includes(j.state)&&Date.now()<deadline){messagePoll=setTimeout(()=>trackMessage(deadline),800);return;}if(['running','queued','stopping'].includes(j.state)){uncertain=true;sendText('sendFeedback','任务仍未结束，已停止本页查询；请读取本次反馈，不会自动重发。');}sendBusy=false;refreshSend();}catch(e){sendBusy=false;uncertain=true;sendText('sendFeedback','反馈读取失败：'+e.message+'。未自动重发；请刷新本次反馈。');refreshSend();}}
async function sendMessage(){refreshSend();if(document.getElementById('sendMessage').disabled)return;const version=sendVersion,settings=clone(draft),hex=payloadHex(),requestId=crypto.randomUUID(),target=edgeMode?window.edgeNeighbors?.selection():null,dst=edgeMode?(target?.name||target?.mac||'未选择设备'):settings.dst;let runSubmitted=false;sendBusy=true;refreshSend();window.routeView?.sending();sendText('sendFeedback','校验 '+(edgeMode?localMAC:settings.src)+' → '+dst+'，'+hex.length/2+' 字节…');try{if(edgeMode){const dstMAC=target?.mac;if(!target?.canSend||!dstMAC)throw Error('请选择可发送的设备，并读取本板最新状态。');if(!await window.edgeNeighbors.verifyTarget(dstMAC))throw Error('本板尚未确认该设备可发送，请刷新邻居。');if(version!==sendVersion)throw Error('读取期间目标、消息或设置已改变；本次未发送。');runSubmitted=true;const r=await api('/api/edge/send',{request_id:requestId,dst:dstMAC,payload_hex:hex});sendText('hardwareRaw',json(r));if(r.state!=='locally_accepted')uncertain=true;window.edgeRouting?.accepted(r,{request_id:requestId,dst:dstMAC,payload_hex:hex});sendText('sendFeedback',r.state==='locally_accepted'?(r.result?.admission_state==='accepted_pending_events'?'本机已接纳，等待板端路由/后续事件；目的收到未确认。':r.result?.admission_state==='locally_queued'?'本机已接纳入队，尚未观测到下一跳提交；目的收到未确认。':'本机已接纳发送；远端目的收到尚未确认。'):'本机发送结果未确认：'+(r.error||r.state));sendBusy=false;refreshSend();return;}const p=await api('/api/hardware/plan',{settings,mode:document.getElementById('algorithm').value==='mid'?'mid':'hops',count:1,payload_hex:hex,request_id:requestId,node_set:[...document.getElementById('nodeSet').value]});const frozen=p.plan||p;if(version!==sendVersion)throw Error('校验期间目标、消息或设置已改变；本次未发送。');if(frozen.payload_hex!==hex||frozen.request_id!==requestId)throw Error('服务未确认本次载荷与请求身份，已停止发送。');if(!frozen.run_available||!frozen.plan_id)throw Error((frozen.availability?.reasons||[]).join('；')||'当前路线不可发送。');sendText('sendFeedback','正在发送给 '+dst+'…');runSubmitted=true;const r=await api('/api/hardware/run',{plan_id:frozen.plan_id,confirm:true});const j=r.run||r;messageRun=j.run_id;hardwareRun=messageRun;document.getElementById('hardwareRead').disabled=!messageRun;document.getElementById('hardwareStop').disabled=!messageRun;if(!messageRun)throw Error('服务未返回任务身份，请查看连接状态；不会自动重发。');messagePoll=setTimeout(()=>trackMessage(Date.now()+120000),400);}catch(e){sendBusy=false;if(runSubmitted){uncertain=true;if(edgeMode)window.edgeRouting?.uncertain({request_id:requestId,dst:target?.mac,payload_hex:hex},e.message);}sendText('sendFeedback','发送未完成：'+e.message+(runSubmitted?'。发包结果不确定，已禁用再次发送；请读取本次反馈。':''));refreshSend();}}
window.edgeNeighbors=(()=>{
  const el=id=>document.getElementById(id),write=(id,v)=>el(id).textContent=v,macRE=/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/;
  let local=null,items=new Map(),fresh=false,listVersion=0,nodeVersion=0,watchTimer=null,watchUntil=0,modeName='unknown',boardBoot=null,serviceInstance=null;
  const cleanMAC=x=>String(x||'').trim().toLowerCase();
  const statuses={heard:'单向收到',bidirectional:'双向已确认',lost:'已超时',unknown:'未确认'};
  function deviceName(r,mac){const given=[r.device_label,r.label,r.name].find(v=>typeof v==='string'&&v.trim());if(given)return given.trim();return Object.entries(local?.labels||snapshot?.labels||{}).find(([,address])=>cleanMAC(address)===mac)?.[0]||'未命名设备';}
  function normalize(r){const mac=cleanMAC(r.node_id),state=r.state;return{...r,mac,name:deviceName(r,mac),state:statuses[state]?state:'unknown',age_ms:Number.isFinite(r.age_ms)?r.age_ms:null,boot:r.boot_id??null,last_seen_ms:r.last_seen_ms??null,readAt:Date.now()};}
  function currentState(r){if(!fresh)return 'unknown';if(modeName==='offline_table')return r.state;const elapsed=Math.max(0,Date.now()-r.readAt);if(r.age_ms!=null&&r.age_ms+elapsed>=(local?.info?.lost_timeout_ms??12000))return 'lost';if(r.state==='bidirectional'&&r.last_seen_ms!=null&&r.age_ms!=null&&r.last_confirmed_ms!=null&&r.last_seen_ms+r.age_ms-r.last_confirmed_ms+elapsed>=(local?.info?.confirm_timeout_ms??9000))return 'heard';return r.state;}
  function stateText(r){return fresh?(statuses[currentState(r)]||statuses.unknown)+(currentState(r)!==r.state?'（按上次记录）':''):'本次读取失败，状态未知';}
  function ageText(r){const age=r.age_ms==null?null:r.age_ms+Math.max(0,Date.now()-(r.readAt||Date.now()));return age==null?'未提供':(age<1000?Math.round(age)+' 毫秒前':(age/1000).toFixed(1)+' 秒前')+(r.last_seen_ms==null?'':'（本板时刻 '+r.last_seen_ms+' ms）');}
  function connected(){return local?.connected!==false&&local?.info?.connected!==false;}
  function available(){return connected()&&local?.info?.radio!==false&&!local?.info?.discovery_fault&&!local?.info?.deployment_fault;}
  function observeHealth(result){if(local?.info&&typeof result.radio==='boolean')local.info.radio=result.radio;}
  function selection(){const automatic=modeName==='autonomous',mac=cleanMAC(automatic?el('autoDestination').value||el('edgeDestination').value:el('edgeDestination').value),r=items.get(mac);return{mac,name:r?r.name+' · '+mac:mac,canSend:macRE.test(mac)&&mac!==cleanMAC(localMAC)&&available()&&fresh&&(automatic||!!r&&(modeName==='offline_table'||currentState(r)==='bidirectional'))};}
  function stop(note){clearTimeout(watchTimer);watchTimer=null;watchUntil=0;write('watchMonitor','开始监测');if(note)write('monitorStatus',note);}
  function options(){for(const id of ['edgeDestination','monitorNode']){const prior=el(id).value,entries=[...items.values()].filter(r=>r.mac!==cleanMAC(localMAC));el(id).replaceChildren(new Option(entries.length?'请选择设备':'尚无设备',''),...entries.map(r=>new Option(r.name+' · '+r.mac+(modeName==='offline_table'?' · 预配置目标':' · '+stateText(r)),r.mac)));if(entries.some(r=>r.mac===prior))el(id).value=prior;}}
  function render(){
    const previousTarget=selection().mac;
    el('neighborRows').replaceChildren();for(const r of items.values()){if(r.mac===cleanMAC(localMAC))continue;const tr=document.createElement('tr');for(const v of [r.name+'\n'+r.mac,ageText(r),modeName==='offline_table'?'预配置名称，非发现证据':stateText(r),r.boot??'未提供']){const td=document.createElement('td');td.textContent=v;tr.append(td);}const td=document.createElement('td'),button=document.createElement('button');button.textContent='选为目的';button.onclick=()=>{el('edgeDestination').value=r.mac;if(modeName==='autonomous')el('autoDestination').value=r.mac;el('monitorNode').value=r.mac;nodeVersion++;stop();messageEdit();};td.append(button);tr.append(td);el('neighborRows').append(tr);}
    options();write('edgeDestinationNote',modeName==='autonomous'?'可填最终目的MAC；板端自行寻路，不向板安装远端路由。':modeName==='offline_table'?'预配置路径模式；下列名称来自已登记地址，不表示已无线发现。':'仅双向确认且未超时的设备可发送；发送前再读取本板记录。');
    el('readMonitor').disabled=!['discovery','autonomous'].includes(modeName);el('watchMonitor').disabled=!['discovery','autonomous'].includes(modeName);if(selection().mac!==previousTarget)messageEdit();else refreshSend();
  }
  function offline(){fresh=connected();items.clear();for(const[name,mac]of Object.entries(local?.labels||snapshot?.labels||{})){const key=cleanMAC(mac);if(macRE.test(key))items.set(key,{mac:key,name,state:'unknown',boot:null,age_ms:null,last_seen_ms:null});}write('neighborStatus','当前使用预配置路径；没有自主发现记录。');render();}
  async function readNeighbors(){
    if(!edgeMode)return;if(modeName==='offline_table')return offline();if(!['discovery','autonomous'].includes(modeName))return write('neighborStatus','本板尚未启用自主发现，请先读取本板状态。');const version=++listVersion;nodeVersion++;
    try{const result=await api('/api/edge/neighbors');if(version!==listVersion||!edgeMode)return;observeHealth(result);const next=new Map();for(const raw of result.neighbors||[]){const r=normalize(raw);if(macRE.test(r.mac))next.set(r.mac,r);}items=next;fresh=true;write('neighborStatus',(items.size?'本板记录 '+items.size+' 个邻居。':'本板尚未收到邻居记录。')+' 读取于 '+new Date().toLocaleTimeString('zh-CN'));render();}
    catch(e){if(version!==listVersion)return;fresh=false;stop();write('neighborStatus','邻居读取失败：'+e.message+'。请读取本板状态。');render();}
  }
  async function readNode(mac,show=true){
    if(!macRE.test(mac))throw Error('请选择设备。');const version=++nodeVersion;listVersion++;
    let result;try{result=await api('/api/edge/nodes/'+mac);}catch(e){if(version!==nodeVersion)return null;throw e;}
    if(version!==nodeVersion||!edgeMode)return null;observeHealth(result);
    const raw=result.node||result.neighbor||result,r=normalize(raw.state==='unknown'&&!raw.node_id?{...raw,node_id:mac}:raw);if(r.mac!==mac)throw Error('服务返回的设备地址不一致。');
    items.set(mac,r);fresh=true;render();
    if(show)write('monitorStatus',r.name+' · '+r.mac+'\n'+stateText(r)+'；最近收到 '+ageText(r)+'；对方启动 '+(r.boot??'未提供')+'。\n来源：本板邻居记录。');
    return r;
  }
  async function monitor(){const mac=cleanMAC(el('monitorNode').value);try{await readNode(mac);}catch(e){fresh=false;stop('本板记录读取失败：'+e.message+'；设备状态未知。');render();}}
  async function tick(){if(!watchUntil||Date.now()>=watchUntil)return stop('本轮5分钟监测已结束，可再次开始。');await monitor();if(watchUntil)watchTimer=setTimeout(tick,2000);}
  function init(s){
    const boot=s.info?.boot_id??s.info?.boot??null,changed=local&&(boot!==boardBoot||s.node_id!==local.node_id||(serviceInstance!=null&&s.instance_id!==serviceInstance));local=s;boardBoot=boot;serviceInstance=s.instance_id??null;document.body.dataset.deployment='local';el('historicalGraph').open=false;el('operation').value='hardware';el('operation').disabled=true;document.body.dataset.operation='hardware';document.querySelector('header h1').textContent='本车无线收发';
    modeName=s.info?.deployment_mode==='autonomous'&&s.routing_supported!==false?'autonomous':s.info?.deployment_mode==='offline_table'?'offline_table':s.info?.deployment_mode==='discovery'?'discovery':'unknown';window.edgeRouting?.init(s);
    write('localBoardInfo','本板 '+s.node_id+' · '+(connected()?'本地已连接':'本地已断开')+'\n启动 '+(boot??'未提供')+' · 模式 '+(modeName==='autonomous'?'板端自动多跳':modeName==='discovery'?'自主一跳发现':modeName==='offline_table'?'预配置多跳':'未启用发现/预配置')+' · 组 '+(s.info?.group??'未提供')+' · 信道 '+(s.info?.channel??'未提供'));
    if(changed){edgeCursor=0;renderInbox([]);write('inboxNote','本地服务或本板启动身份已变化；这里只显示本次会话收件，旧记录查看事件日志。');messageEdit();listVersion++;nodeVersion++;items.clear();fresh=false;stop('本板启动身份已变化，请重新读取邻居。');}
    if(modeName==='offline_table')offline();else if(['discovery','autonomous'].includes(modeName))readNeighbors();else{fresh=false;write('neighborStatus','本板尚未声明自主发现模式；请按部署指南配置并启动。');render();}
  }
  el('refreshNeighbors').onclick=readNeighbors;el('refreshLocalBoard').onclick=senderStatus;el('readMonitor').onclick=monitor;
  el('edgeDestination').onchange=()=>{if(modeName==='autonomous')el('autoDestination').value=el('edgeDestination').value;nodeVersion++;stop();messageEdit();window.edgeRouting?.targetChanged();};el('autoDestination').oninput=()=>{nodeVersion++;stop();messageEdit();window.edgeRouting?.targetChanged();};el('monitorNode').onchange=()=>{nodeVersion++;stop('关注设备已改，请读取本板记录。');};
  el('watchMonitor').onclick=()=>{if(watchUntil)return stop('监测已停止。');if(!el('monitorNode').value)return write('monitorStatus','请选择关注设备。');watchUntil=Date.now()+300000;write('watchMonitor','停止监测');tick();};
  window.addEventListener('pagehide',()=>{listVersion++;nodeVersion++;stop();});
  document.addEventListener('capabilitieschange',()=>{if(!edgeMode){listVersion++;nodeVersion++;fresh=false;stop();}});
  return{init,selection,readNeighbors,disconnect:reason=>{listVersion++;nodeVersion++;if(local)local.connected=false;fresh=false;window.edgeRouting?.disconnect(reason);stop('本板连接中断：'+reason);write('localBoardInfo','本板 '+(local?.node_id||localMAC)+' · 未连接；当前邻居状态未知。');render();},verifyTarget:async mac=>{if(modeName==='offline_table')return selection().canSend;if(modeName==='autonomous'){const s=await api('/api/edge/status');init(s);return modeName==='autonomous'&&selection().mac===mac&&available()&&macRE.test(mac);}try{const r=await readNode(mac,false);return !!r&&currentState(r)==='bidirectional'&&available();}catch(e){fresh=false;render();throw e;}}};
})();
document.getElementById('sendMessage').onclick=sendMessage;document.getElementById('readMessages').onclick=async()=>{if(messageRun){await readMessageRun().catch(e=>sendText('sendFeedback',e.message));}else if(edgeMode){await Promise.all([senderStatus(),receiveMessages()]);}else await senderStatus();};document.getElementById('readInbox').onclick=receiveMessages;document.getElementById('operation').onchange=operation;for(const id of ['message','messageHex','hexMode'])document.getElementById(id).addEventListener('input',messageEdit);document.getElementById('hexMode').addEventListener('change',()=>{document.getElementById('hexDetails').open=document.getElementById('hexMode').checked;messageEdit();});for(const id of ['nodeSet','src','dst','hops','algorithm','nodeTarget','twoWay','success','delay','capacity','connected','fail','duration','seed','start','end','bothDirections'])document.getElementById(id).addEventListener('change',messageEdit);document.getElementById('graph').addEventListener('click',messageEdit);document.getElementById('reset').addEventListener('click',()=>{messageEdit();setTimeout(refreshSend,300);});
document.getElementById('hardwareStatus').onclick=()=>edgeMode?senderStatus():hardwareStatus();
document.addEventListener('draftchange',()=>{if(document.body.dataset.operation==='hardware'&&['latency_aware','fixed'].includes(document.getElementById('algorithm').value))document.getElementById('algorithm').value='hops';messageEdit();});operation();senderStatus();

// BOARD_ROUTE_MODEL_BEGIN: canonical evidence reducer, independent of transport/DOM.
window.BoardRouteEvidence=(()=>{
  const macRE=/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/,mac=x=>String(x||'').toLowerCase(),copy=x=>JSON.parse(JSON.stringify(x));
  const uint=x=>Number.isInteger(x)&&x>0&&x<=4294967295,hex=x=>typeof x==='string'&&/^(?:[a-fA-F0-9]{2}){0,160}$/.test(x);
  function identity(x){if(!x)return null;const value={origin:mac(x.origin),origin_boot:x.origin_boot,seq:x.seq,dst:mac(x.dst)};return macRE.test(value.origin)&&macRE.test(value.dst)&&uint(value.origin_boot)&&uint(value.seq)?value:null;}
  const packetKey=x=>{const id=identity(x);return id?[id.origin,id.origin_boot,id.seq,id.dst].join('/'):null;};
  function path(value,origin,dst){if(!Array.isArray(value)||value.length<2||value.length>5)return null;const p=value.map(mac);return p.every(n=>macRE.test(n))&&new Set(p).size===p.length&&(!origin||p[0]===mac(origin))&&(!dst||p.at(-1)===mac(dst))?p:null;}
  function create(local){return{local:mac(local),routes:[],packets:{},packet_order:[],requests:{},seen:[],logs:[],warnings:[]};}
  function ensure(s,id){const key=packetKey(id);if(!key)return null;if(!s.packets[key]){s.packets[key]={identity:identity(id),stage:'observed',observations:[],header_paths:[],rounds:[],destination_received:false,proof_errors:[]};s.packet_order.push(key);if(s.packet_order.length>64)delete s.packets[s.packet_order.shift()];}return s.packets[key];}
  function accept(state,request_id,result,request){const s=copy(state),candidate=identity(result),id=candidate&&candidate.origin===s.local?candidate:null,p=id&&ensure(s,id);s.requests[request_id]={request:copy(request),identity:id,source:'local_command_acceptance'};if(!p){s.warnings.push('本地回执缺少完整包身份；未关联路径或交付。');return s;}p.request_id=request_id;p.expected_hex=String(request.payload_hex).toLowerCase();p.stage=['next_hop_queued','locally_queued'].includes(result.admission_state)?result.admission_state:'accepted_pending_events';
    if(p.destination_received&&p.destination_payload_hex!==p.expected_hex){p.destination_received=false;p.proof_errors.push('目的字节与本次载荷不相同。');}return s;}
  function apply(state,event){
    const s=copy(state);if(event.event_id&&s.seen.includes(event.event_id))return s;if(event.event_id){s.seen.push(event.event_id);if(s.seen.length>2048)s.seen.shift();}
    s.logs.push(copy(event));if(s.logs.length>256)s.logs.shift();
    if(event.kind==='selected'){
      const p=path(event.path,event.origin,event.dst);if(!p){s.warnings.push('板端选路事件的完整路径无效，未补猜缺段。');return s;}
      const value={origin:mac(event.origin||p[0]),origin_boot:event.origin_boot??null,dst:mac(event.dst||p.at(-1)),round:event.round??null,path:p,valid:true,source:'board_selected_event',event_id:event.event_id,raw:event.raw||null};
      const same=s.routes.find(r=>r.origin===value.origin&&r.origin_boot===value.origin_boot&&r.dst===value.dst&&r.round===value.round&&JSON.stringify(r.path)===JSON.stringify(value.path));if(!same){const peers=s.routes.filter(r=>r.origin===value.origin&&r.origin_boot===value.origin_boot&&r.dst===value.dst&&r.round===value.round);if(peers.length){for(const r of peers)r.conflict=true;value.conflict=true;s.warnings.push('同一轮存在不同的选路事件，未认定新的整包路径。');}s.routes.push(value);}if(s.routes.length>64)s.routes.shift();return s;
    }
    if(event.kind==='invalidated'){
      if(!event.round){s.warnings.push('失效事件缺轮次，未改写已有路由状态。');return s;}
      const invalidPath=path(event.path,event.origin,event.dst),edge=(event.failed_edge||[]).map(mac);
      for(const route of s.routes){const endpoints=(!event.origin||route.origin===mac(event.origin))&&(!event.dst||route.dst===mac(event.dst))&&(event.origin_boot==null||route.origin_boot===event.origin_boot),round=event.round==null||event.round===0||route.round===event.round,proof=invalidPath?JSON.stringify(invalidPath)===JSON.stringify(route.path):edge.length===2&&route.path.some((n,i)=>i&&route.path[i-1]===edge[0]&&n===edge[1]);if(endpoints&&round&&proof){route.valid=false;route.reason=event.reason||'板端路由失效事件';route.invalidated_event=event.event_id;}}
      return s;
    }
    if(!['data_tx','relay_rx','destination_rx','waiting','no_route','local_drop','delivery_unknown','cancelled','queued','accepted_event'].includes(event.kind))return s;
    if(['data_tx','relay_rx'].includes(event.kind)&&event.packet_kind!=='DATA')return s;
    const id=identity(event.identity),p=id&&ensure(s,id);if(!p)return s;
    if(['data_tx','relay_rx'].includes(event.kind)){
      if(event.packet_kind!=='DATA')return s;
      const node=mac(event.node),next=mac(event.next_hop);if(!macRE.test(node)||node!==s.local)return s;
      p.observations.push({kind:event.kind,node,...(macRE.test(next)?{next_hop:next}:{}),event_id:event.event_id,source:'local_board_event'});if(p.observations.length>64)p.observations.shift();
      const h=path(event.path,id.origin,id.dst);if(h&&!p.header_paths.some(v=>JSON.stringify(v)===JSON.stringify(h)))p.header_paths.push(h);if(p.header_paths.length>1){p.header_conflict=true;if(!p.proof_errors.includes('同包记录了不同路径，未改写旧包。'))p.proof_errors.push('同包记录了不同路径，未改写旧包。');}
      if(event.kind==='data_tx')p.stage='local_data_submitted';return s;
    }
    if(event.kind==='destination_rx'){
      if(mac(event.node)!==id.dst||mac(event.node)!==s.local||!hex(event.payload_hex)){p.proof_errors.push('目的接收事件缺少本板目的身份或原字节。');return s;}
      const payload=event.payload_hex.toLowerCase();if(p.expected_hex!=null&&payload!==p.expected_hex){p.proof_errors.push('目的字节与本次载荷不相同。');return s;}
      const h=path(event.path,id.origin,id.dst);if(h&&!p.header_paths.some(v=>JSON.stringify(v)===JSON.stringify(h)))p.header_paths.push(h);if(p.header_paths.length>1){p.header_conflict=true;if(!p.proof_errors.includes('同包记录了不同路径，未改写旧包。'))p.proof_errors.push('同包记录了不同路径，未改写旧包。');}p.destination_received=true;p.destination_payload_hex=payload;p.destination_event=event.event_id;p.stage='destination_received';return s;
    }
    if(event.kind==='waiting'&&event.round&&!p.rounds.includes(event.round))p.rounds.push(event.round);
    if(event.kind==='queued'){p.stage=macRE.test(mac(event.next_hop))?'next_hop_queued':'locally_queued';return s;}
    const stages={cancelled:'cancelled_by_stop',accepted_event:'locally_queued',waiting:'waiting_route',no_route:'no_route',local_drop:'local_drop',delivery_unknown:'delivery_unknown',queued:'next_hop_queued'};if(stages[event.kind])p.stage=stages[event.kind];return s;
  }
  return{create,accept,apply,identity,packetKey,path};
})();
// BOARD_ROUTE_MODEL_END

// BOARD_ROUTE_VIEW_BEGIN: local native events only; never calls a planner.
window.edgeRouting=(()=>{
  const el=id=>document.getElementById(id),write=(id,v)=>el(id).textContent=v,M=window.BoardRouteEvidence;
  let enabled=false,status=null,instance=null,cursor=0,version=0,reading=false,readAgain=false,watchTimer=null,watchUntil=0,state=M.create(''),cache=null,selected='',lastRequest=null,oldSessions=[],boundary=0;
  const mode=s=>s?.mode==='single_local_board'&&s.info?.deployment_mode==='autonomous'&&s.routing_supported!==false;
  const destination=()=>window.edgeNeighbors?.selection()?.mac||'';
  const stageNames={observed:'仅有本板事件',locally_queued:'本地已接纳入队，下一跳尚未确认',accepted_pending_events:'本地已接纳，等待板端后续事件',waiting_route:'板端等待寻路',next_hop_queued:'已排到具体下一跳',local_data_submitted:'本板DATA已提交无线接口',no_route:'板端报告本轮无路',cancelled_by_stop:'板端记录stop取消，未按无路截止处理',local_drop:'本板记录丢弃',delivery_unknown:'板端记录交付未知',destination_received:'本板作为目的端已收到原字节'};
  const title=id=>id.origin+' / '+id.origin_boot+' / '+id.seq+' → '+id.dst;
  function stop(note){clearTimeout(watchTimer);watchTimer=null;watchUntil=0;write('watchBoardRoutes','跟踪30秒');if(note)write('boardRouteReadStatus',note);}
  function native(raw){
    if(raw.node_id&&String(raw.node_id).toLowerCase()!==state.local)return null;if(raw.boot_id!=null&&status?.info?.boot_id!=null&&raw.boot_id!==status.info.boot_id)return null;if(raw.edge_cursor!=null&&raw.edge_cursor<=boundary)return null;
    const map={route_selected:'selected',route_invalidated:'invalidated',route_waiting:'waiting',route_no_route:'no_route',route_drop:'local_drop',delivery_unknown:'delivery_unknown',tx_submit:'data_tx',rx_relay:'relay_rx',rx_local:'destination_rx',tx_queued:'queued',route_accepted:'accepted_event',route_request:'request',route_candidate:'candidate'};
    const kind=raw.event==='route_no_route'&&raw.reason===6?'cancelled':map[raw.event];if(!kind)return null;
    // E1's autonomous serializer emits these three names for DATA only. Explicit
    // packet_kind, when present, takes precedence and controls are rejected.
    const packet_kind=raw.packet_kind??(['tx_submit','rx_relay','rx_local'].includes(raw.event)?'DATA':null);
    return{kind,event_id:(instance||'local')+'/'+(raw.edge_cursor??JSON.stringify([raw.event,raw.monotonic_ms,raw.origin,raw.seq,raw.request,raw.path])),node:raw.node_id,origin:raw.origin,origin_boot:raw.origin_boot,dst:raw.dst,identity:M.identity(raw),round:raw.request??null,path:raw.path,failed_edge:raw.failed_edge,reason:raw.reason==null?null:'原因码 '+raw.reason,packet_kind:typeof packet_kind==='string'?packet_kind.toUpperCase():packet_kind,next_hop:raw.next_hop,payload_hex:raw.payload_hex,raw};
  }
  function consume(events){for(const raw of events||[]){const event=native(raw);if(event)state=M.apply(state,event);}}
  function matchedRoute(p){if(!p)return null;return state.routes.filter(r=>r.origin===p.identity.origin&&r.origin_boot===p.identity.origin_boot&&r.dst===p.identity.dst&&p.rounds.includes(r.round)).at(-1);}
  function render(){
    if(!enabled)return;const wanted=selected||el('boardPacket').value;
    el('boardPacket').replaceChildren(new Option('选择本板消息',''),...state.packet_order.map(k=>new Option(title(state.packets[k].identity),k)));
    selected=state.packets[wanted]?wanted:'';el('boardPacket').value=selected;
    const p=state.packets[selected],dst=p?.identity.dst||destination(),route=matchedRoute(p),cacheRow=(cache?.routes||[]).find(r=>String(r.dst).toLowerCase()===dst&&M.path(r.path,state.local,dst)),header=p?.header_paths.at(-1);
    let chosen=null,source='尚无与本包关联的选路事件。';
    if(p?.header_conflict||route?.conflict){source='同包/同轮路径记录冲突，未选新路改写旧包。';}
    else if(header){chosen=header;source='本包DATA头的路径（本板观测，不等于全链接收）。';}
    else if(route){chosen=route.path;source='本包等待轮次 '+route.round+' 的板端选路事件'+(route.valid?'。':'；该路径后有失效记录。');}
    else if(cacheRow&&!p){chosen=M.path(cacheRow.path,state.local,dst);source='读取时本板缓存；尚未关联到本包。轮次 '+cacheRow.request+'，本板到期时刻 '+cacheRow.expires_ms+' ms。';}
    else if(!p){const latest=state.routes.filter(r=>!dst||r.dst===dst).at(-1);if(latest){chosen=latest.path;source='最近板端选路事件，尚未关联到具体本页消息'+(latest.valid?'。':'；后有失效记录。');}}
    write('boardSelectedPath',source+(chosen?'\n'+chosen.join(' → '):''));write('boardCurrentCache',cacheRow?'本板只读缓存，轮次 '+cacheRow.request+'，到期本板时刻 '+cacheRow.expires_ms+' ms；不是本包路径证据。\n'+cacheRow.path.join(' → '):'读取时未返回该目的缓存；不能由旧选择或PC候选补齐。');
    if(p){write('boardPacketStatus',title(p.identity)+'\n'+(p.destination_received?stageNames.destination_received:stageNames[p.stage]||p.stage)+'。'+(p.destination_received?' 原字节 '+p.destination_payload_hex:' 目的交付未确认；没有端点证据不会标已送达。')+(p.proof_errors.length?'\n证据缺项：'+p.proof_errors.join('；'):''));
      write('boardObserved',p.observations.length?p.observations.map(e=>e.kind==='data_tx'?'本板提交 '+e.node+' → '+(e.next_hop||'下一跳未记录')+'（不是远端接收）':'本板中继收到 '+e.node).join('\n'):'本包尚无本板DATA提交/中继接收记录。');
    }else{write('boardPacketStatus',lastRequest&&!selected?'本次请求 '+lastRequest+'；尚未关联到完整包身份，不能认定发出或交付。':'选择本板消息查看本地进度。');write('boardObserved','这里只显示本板事件；没有远端日志就没有完整沿途实收链。');}
    el('boardRouteHistory').replaceChildren();for(const r of state.routes.slice(-16)){const row=document.createElement('div');row.textContent='轮次 '+(r.round??'未记录')+' · '+r.origin+' / '+r.origin_boot+' → '+r.dst+'\n'+r.path.join(' → ')+' · '+(r.valid?'板端曾选择，当前可用性另读缓存':'已失效：'+r.reason);el('boardRouteHistory').append(row);}
    if(!state.routes.length)write('boardRouteHistory','没有选路/失效事件，未用缓存或PC候选补历史。');
    write('boardRouteRaw',json({source:'local_board_events_and_readonly_cache',status,instance_id:instance,cursor,selected,state,cache,previous_sessions:oldSessions}));
  }
  function init(s){
    const next=mode(s),changed=status&&(s.node_id!==status.node_id||s.info?.boot_id!==status.info?.boot_id||s.instance_id!==instance||s.info?.deployment_mode!==status.info?.deployment_mode);status=s;enabled=next;document.body.dataset.boardRouting=enabled?'autonomous':'manual';window.adhocEntry?.status(s);
    if(!enabled){version++;stop();return;}
    if(changed||!state.local){if(state.local){oldSessions.push({local:state.local,instance_id:instance,state});if(oldSessions.length>3)oldSessions.shift();}version++;stop();state=M.create(s.node_id);cache=null;cursor=0;boundary=0;selected='';lastRequest=null;}
    instance=s.instance_id??null;write('boardRouteSource','本板 '+s.node_id+' · 自动多跳。路径由板端计算，主机仅交最终目的/载荷；本地接纳与目的交付分开。');render();
    if(changed||cursor===0){if(reading)readAgain=true;else read();}
  }
  function accepted(record,request){
    if(!enabled)return;
    if(record.request?.request_id!==request.request_id||record.request?.dst!==request.dst||record.request?.payload_hex!==request.payload_hex)throw Error('本地服务未返回与本次目标/载荷相同的请求绑定。');
    lastRequest=request.request_id;selected='';
    if(record.state==='locally_accepted'){const id=M.identity(record.result);if(!id||id.origin!==state.local||id.dst!==request.dst)throw Error('本地接纳回执缺完整原包身份。');state=M.accept(state,request.request_id,record.result,request);selected=M.packetKey(id);}else state.requests[request.request_id]={request,identity:null,source:'submission_outcome_unknown',error:record.error||record.state};
    render();read();
  }
  async function read(){
    if(!enabled)return;if(reading){readAgain=true;return;}reading=true;const token=++version,request=lastRequest;
    try{
      const urls=['/api/edge/events?after='+cursor+'&wait=0','/api/edge/routes'];if(request)urls.push('/api/edge/requests/'+request);
      const result=await Promise.allSettled(urls.map(url=>api(url)));if(token!==version||!enabled)return;
      const e=result[0];if(e.status!=='fulfilled')throw e.reason;
      if(e.value.instance_id&&instance&&e.value.instance_id!==instance){write('boardRouteReadStatus','本地服务会话已变化，重新读取本板身份。');await senderStatus();return;}
      const starts=(e.value.events||[]).filter(x=>x.event==='command_result'&&x.ok===true&&['route_config','route_start'].includes(x.cmd)&&x.deployment_mode==='autonomous');const latest=Math.max(0,...starts.map(x=>x.edge_cursor||0));if(latest>boundary){if(boundary){oldSessions.push({local:state.local,instance_id:instance,state});if(oldSessions.length>3)oldSessions.shift();state=M.create(status.node_id);selected='';lastRequest=null;cache=null;}boundary=latest;}consume(e.value.events);cursor=e.value.cursor??cursor;
      cache=result[1].status==='fulfilled'&&result[1].value.source==='local_board_cache'&&result[1].value.host_planner_used===false?result[1].value:null;
      if(result[2]?.status==='fulfilled'){
        const r=result[2].value,original=state.requests[request]?.request;
        if(original&&(r.request?.request_id!==request||r.request?.dst!==original.dst||r.request?.payload_hex!==original.payload_hex))throw Error('查询回执与原请求目标/载荷不一致。');
        consume(r.progress?.route_history);consume(r.progress?.events);consume(r.progress?.destination_evidence);
      }
      write('boardRouteReadStatus','已读本板事件至游标 '+cursor+'；缓存为本板只读查询，不是PC规划。'+(result[1].status==='rejected'?' 缓存读取失败，未补猜路径。':'')+(result[2]?.status==='rejected'?' 原请求进度读取失败，保留原身份。':''));render();
    }catch(e){if(token===version){cache=null;stop('路由读取失败：'+e.message+'；未补发业务包。若游标过期，请刷新页面读保留片段，完整记录查本地日志。');render();}}
    finally{reading=false;if(readAgain&&enabled){readAgain=false;read();}}
  }
  async function tick(){if(!enabled||!watchUntil)return;if(Date.now()>=watchUntil)return stop('30秒本地观察结束；这不是板端无路结论，也不会自动重发。');await read();if(watchUntil)watchTimer=setTimeout(tick,1000);}
  el('readBoardRoutes').onclick=read;el('watchBoardRoutes').onclick=()=>{if(watchUntil)return stop('已停止本地跟踪。');watchUntil=Date.now()+30000;write('watchBoardRoutes','停止跟踪');tick();};
  el('boardPacket').onchange=()=>{selected=el('boardPacket').value;render();};window.addEventListener('pagehide',()=>{version++;stop();});
  return{init,accepted,uncertain:(request,error)=>{if(!enabled)return;lastRequest=request.request_id;selected='';state.requests[request.request_id]={request,identity:null,source:'submission_outcome_unknown',error};render();},targetChanged:()=>{selected=state.packet_order.findLast(k=>state.packets[k].identity.dst===destination())||'';render();},disconnect:reason=>{version++;cache=null;stop('本板连接中断：'+reason);render();}};
})();
// BOARD_ROUTE_VIEW_END

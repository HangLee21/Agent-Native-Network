'use strict';
(()=>{
  const M=MobileMapModel,S=MobileStudioModel,L=MobileLoRaModel,$=id=>document.getElementById(id),ns='http://www.w3.org/2000/svg';
  const colors={green:'#17816c',blue:'#4283b0',red:'#c26853',gray:'#91a0a4',purple:'#8759a6'};
  let model=M.create(),selected='',timer=null,observing=true,inFlight=false,version=0,instance=null,cursor=0,baseKey=null;
  let origin=null,view=null,zoom=1,autoFit=true,logical=new Map(),layoutKey='',packetRows=[],selectedPacket='',positions=new Map(),topology=true,animated=new Set(),pendingAnimation=[];
  let snapshotLoaded=false,snapshotError='',health=null,radioExpiry=null;
  let packetLog=S.createPacketLog(),selectedEdge='',timelineTruncated=false;
  let loraData=null,loraReadAt=0,loraError='',loraVersion=0,loraLoading=false,replayFrames=null,replayTimer=null,replayId=null,replayTotal=0,replayOffset=0,replayRequestSeq=0,replayPlaying=false,replayDisplayed=0,replayTimestamp=null;
  let gatewaySeen=false,gatewayInterrupted=false,gatewayRecovery='正在连接网关';
  let sourceState=null,sourceId=null,sourceEpoch=null,sourceRequest=0,sourceBusy=false;
  let shownSource='wifi';const sourceViews=new Map();let manualKey='',manualPositions=new Map(),suppressClick=false;try{const v=localStorage.getItem('mobile.topology.source');if(['wifi','lora'].includes(v))$('topologySource').value=v;}catch(_){}shownSource=$('topologySource').value;
  try{const mode=localStorage.getItem('mobile.layout.mode');if(['clear','manual','gps'].includes(mode))$('layoutMode').value=mode;}catch(_){}
  const isLoRa=()=>$('topologySource').value==='lora';
  let loraCache=null;const lora=()=>{const t=now(),bucket=replayFrames?0:Math.floor(t/1000),stale=!!loraError||!replayFrames&&!!loraData&&t-loraReadAt>6000;if(!loraCache||loraCache.data!==loraData||loraCache.bucket!==bucket||loraCache.stale!==stale||loraCache.fleet!==fleetLabels)loraCache={data:loraData,bucket,stale,fleet:fleetLabels,value:L.snapshot(loraData,replayFrames?0:Math.max(0,t-loraReadAt),replayFrames?[]:[...fleetLabels.keys()],stale)};return loraCache.value;};
  const radioEdges=()=>isLoRa()?lora().edges:M.edges(model,now()).filter(e=>e.hasObservation!==false);
  const graphNodes=()=>isLoRa()?[...lora().nodes.values()].map(n=>{const gps=n.report?.report?.gps,valid=gps?.valid===true&&Number.isFinite(gps.lat_e7)&&Number.isFinite(gps.lon_e7)&&Math.abs(gps.lat_e7)<=850000000&&Math.abs(gps.lon_e7)<=1800000000,base=replayFrames?{}:model.nodes.get(n.id)||{};return {...base,...n,...(valid?{position:{lat:gps.lat_e7/1e7,lon:gps.lon_e7/1e7,valid:true,age_ms:Number.isFinite(n.report.gps_age_ms??n.report.report.gps_age_ms)?(n.report.gps_age_ms??n.report.report.gps_age_ms)+(replayFrames?0:Math.max(0,now()-loraReadAt)):(n.report.age??0),source:'gps'},loadedAt:now(),projectedAges:true,stale_after_ms:30000}:gps||replayFrames?{position:null}: {})};}):[...model.nodes.values()];
  const age=x=>Number.isFinite(x)?x<1000?Math.round(x)+' ms':(x/1000).toFixed(1)+' s':'未知';
  const source=x=>({simulated:'模拟',fake:'模拟',fake_gps:'模拟 GPS',gpsd:'GPSD',gps:'真实 GPS',measured:'实测',unavailable:'不可用',host_model:'主机模型',board_field_agent:'板内发生器',actual_E2_fake_agent_function_processes:'E2 fake_agent 进程',E2_fake_agent_function_host_model:'E2 fake_agent（主机模型）'}[x]||x||'未提供');
  let fleetLabels=new Map(),fleetGeneration=0,nextFleetRead=0;
  const label=id=>{const key=M.clean(id),registered=fleetLabels.get(key),reported=lora().labels.get(key)||model.nodes.get(key)?.label;return registered!==undefined?String(registered):typeof reported==='string'&&reported.trim()?reported.trim():FleetLabels.label(fleetLabels,id)??(key||'网关 / 未知');};
  function fleetLoad(value){fleetLabels=FleetLabels.parse(value);$('fleetStatus').textContent='节点编号配置已加载 · '+fleetLabels.size+' 个';$('fleetStatus').classList.remove('fleetError');render();}
  function fleetFail(error){fleetLabels=new Map();$('fleetStatus').textContent='节点编号暂不可用，正在自动重试；如持续无法恢复，请重新打开启动入口。原因：'+error;$('fleetStatus').classList.add('fleetError');render();}
  async function fetchFleet(){const ticket=++fleetGeneration;try{const res=await fetch('/api/v1/fleet',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!res.ok)throw Error('HTTP '+res.status);const body=await res.json();if(ticket===fleetGeneration)fleetLoad(body);}catch(e){if(ticket===fleetGeneration)fleetFail(e.message);}}
  const text=(id,value)=>$(id).textContent=value,now=()=>performance.now();
  function svg(tag,attrs={},content){const el=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,v);if(content!==undefined)el.textContent=content;return el;}
  function html(tag,content,cls){const e=document.createElement(tag);e.textContent=content;if(cls)e.className=cls;return e;}
  let agingTimer=null;
  const sampleState=x=>({heard:'采样时单向听到',bidirectional:'采样时本端确认',lost:'采样时已失效'}[x]||'采样状态未知');
  const SAMPLE_COLOR={bidirectional:'#168269',heard:'#237fbe',lost:'#b3261e',unknown:'#a7b1b5'};
  const radioInfo=e=>isLoRa()?e.historical?{label:'历史记录 · 当前不可确认',color:'#919b9e'}:{label:sampleState(e.state),color:SAMPLE_COLOR[e.state]||'#8d9a9e'}:S.edgeInfo(e);
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
    for(const [name,color] of [['节点：LoRa 在线','#8056ad'],['节点：仅被邻居看到','#aa7021'],['节点：采样已失效','#b3261e'],['节点：网关（接收端）','#1f6f78']]){
      const chip=html('span','','legendChip'),dot=html('i','','legendDot');
      dot.style.background=color;chip.append(dot,html('span',name));box.append(chip);
    }
  }
  function renderLoRa(){
    const enabled=isLoRa(),data=lora();$('loraStatus').classList.toggle('hidden',!enabled);$('wifiLegend').classList.toggle('hidden',enabled);$('loraLegend').classList.toggle('hidden',!enabled);$('chartLegendLora').classList.toggle('hidden',!enabled);$('chartLegendWifi').classList.toggle('hidden',enabled);if(!enabled)return;
    renderLoRaLegend();
    const counts={reported:0,stale_report:0,interrupted:0,never:0};for(const n of data.nodes.values())if(Object.hasOwn(counts,n.status))counts[n.status]++;
    const worker=data.receiver?.worker_state,localUnreachable=data.receiver?.local_receiver_unreachable===true,workerProblem=['starting','recovering','stopped'].includes(worker),workerUnknown=!replayFrames&&(!!loraError||!!loraData&&now()-loraReadAt>6000||!localUnreachable&&loraData?.control?.reason==='接收来源未响应');
    const gatewayText=localUnreachable&&!workerUnknown?'本机接收服务未响应':workerUnknown&&(worker||localUnreachable)?'网关当前状态未知':workerProblem?'接收线程未就绪，网关心跳当前不可确认':worker==='running'&&data.receiver?.gateway_observed===false?'网关心跳未观测到或已超时':gatewayRecovery;
    text('recoveryStatus',(data.receiver?.mode==='node_serial'?'节点 '+label(data.receiver.gateway_id)+' 串口接收 · ':'')+gatewayText+` · 在线 ${counts.reported} / 超时未见 ${counts.stale_report} / 观测中断 ${counts.interrupted} / 从未观测 ${counts.never} · 超时阈值按上报周期计算`);
    const workerLabels={running:'接收线程运行中',starting:'接收线程启动中',recovering:'接收线程恢复中',stopped:'接收线程已停止'};
    const workerStatus=$('receiverWorkerStatus');workerStatus.classList.toggle('hidden',!worker&&!localUnreachable);workerStatus.dataset.state=workerUnknown||localUnreachable?'unknown':worker;
    if(worker||localUnreachable)text('receiverWorkerStatus',(replayFrames?'历史快照 · ':'')+(workerUnknown?'接收线程当前状态未知 · 来源读取失败或快照过期':localUnreachable?'本机接收服务未响应':workerLabels[worker]||'接收线程状态未知'));
    const serialConfig=data.receiver?.mode==='node_serial';
    const newest=data.reports.slice().filter(x=>Number.isFinite(x.age)).sort((a,b)=>a.age-b.age)[0],radio=newest?.lora;
    const summary=$('uplinkSummary');summary.replaceChildren();
    if(radio){
      const grid=html('dl','','uplinkGrid');
      for(const [name,value] of [['上行信道',radio.channel!=null?'CH '+radio.channel:'未提供'],['频率',Number.isFinite(radio.frequency_hz)?(radio.frequency_hz/1000000).toFixed(3)+' MHz':'未提供'],[serialConfig?'扩频因子（接收配置）':'扩频因子',Number.isInteger(radio.sf)?'SF'+radio.sf:'未提供'],[serialConfig?'带宽（接收配置）':'带宽',Number.isFinite(radio.bandwidth_hz)?(radio.bandwidth_hz/1000)+' kHz':'未提供'],['接收信号',Number.isFinite(radio.rssi_dbm)?radio.rssi_dbm+' dBm':'未提供'],['信噪比',Number.isFinite(radio.snr_db)?radio.snr_db+' dB':'未提供'],['距上次上报',age(newest.age)]]){
        const cell=html('div','');cell.append(html('dt',name),html('dd',value));grid.append(cell);
      }
      summary.append(grid,html('small',(replayFrames?'历史采样 · ':'接收来源 · ')+label(newest.id)+(serialConfig?' · 接收节点配置':' · 网关逐帧元数据')));
    }else summary.append(html('span','LoRa 上行：尚无报告'));
    const r=data.receiver,offline=['stale','unavailable','busy','error'].includes(r?.state)||!!loraError||workerProblem||localUnreachable,stateName={idle:'未开始接收',connecting:'正在连接',receiving:'正在实收',stale:'暂未续收',unavailable:'接收器不可用',busy:'串口已占用',error:'读取异常'};
    const waitingForReports=!replayFrames&&!workerUnknown&&!localUnreachable&&worker==='running'&&r?.gateway_observed===true&&['idle','receiving','stale'].includes(r.state)&&loraData?.reports?.length===data.reports.length&&data.reports.every(item=>Number.isFinite(item.age)&&data.nodes.get(item.id)?.status==='stale_report');
    $('loraStatus').classList.toggle('warning',offline);text('loraTitle',replayFrames?`历史接收器 ${r?.gateway_id?label(r.gateway_id):'未提供'} · 采样时 ${localUnreachable?'本机接收服务未响应':workerProblem?workerLabels[worker]:stateName[r?.state]||'状态未知'}`:loraError?'LoRa 来源暂时不可读取':r?`LoRa 接收器 ${r.gateway_id?label(r.gateway_id):'待识别'} · ${workerUnknown&&(worker||localUnreachable)?'状态未知':localUnreachable?'本机接收服务未响应':workerProblem?workerLabels[worker]:waitingForReports?'网关在线，等待节点上报':r.gateway_observed===false?'等待网关连接':stateName[r.state]||'状态未提供'}`:loraLoading?'正在读取 LoRa 来源':'尚无 LoRa 接收器报告');
    text('loraNote',(loraError?loraError+(loraData?'；保留上次快照。':'；等待当前来源快照。'):'')+(r?.error?r.error+'。':'')+`已取得 ${data.reports.length} 个报告者的最近快照。板间箭头为 ESP-NOW 邻居；LoRa 仅回传这些快照。位置、agent 和业务仍使用原来源。`);
    $('loraReports').replaceChildren();for(const item of data.reports){const p=item.report,g=item.gateway_id||r?.node_id||r?.gateway_id,b=html('button',`${label(item.id)} → ${g?label(g):'接收器未提供'} · LoRa RSSI ${Number.isFinite(item.lora?.rssi_dbm)?item.lora.rssi_dbm+' dBm':'未提供'} / SNR ${Number.isFinite(item.lora?.snr_db)?item.lora.snr_db+' dB':'未提供'}`,'loraReport');
      b.append(html('small',`报告 #${p.report_seq??'未提供'} · boot ${p.observer_boot??'未提供'} · PC 收报距今 ${age(item.age)} · 邻居 ${p.neighbors?.length||0}/${p.total_rows??'?'}${p.truncated?'（截断）':''}${p.nd_table_full?' · ND 表曾满':''}`));b.onclick=()=>choose(item.id);$('loraReports').append(b);
    }if(!data.reports.length)text('loraReports',offline?'接收器离线或不可读取；等待恢复，未从 Wi-Fi 补充邻居。':'尚未取得实际 LoRa 帧；等待报告，不用 Wi-Fi 邻居填充。');
  }
  function showSources(data){
    sourceState=data;const select=$('receiverSource'),old=data.selection==='manual'?data.preferred_source_id||'':'',items=data.sources;
    select.replaceChildren(new Option('自动选择',''));for(const item of items){const selectable=item.verified===true&&item.capabilities?.receive===true,description=!item.verified?'未验证':item.capabilities?.receive!==true?'不支持接收':item.available===true?'可接收':'暂不可用';const opt=new Option(`${item.label||item.id} · ${description}`,item.id);opt.disabled=!selectable&&item.id!==old;select.add(opt);}select.value=old;select.disabled=sourceBusy;
    const current=items.find(x=>x.id===data.selected_source_id),preferred=items.find(x=>x.id===data.preferred_source_id),mode=data.selection==='manual'?`手动优先：${preferred?.label||data.preferred_source_id||'未知'}${data.selected_source_id!==data.preferred_source_id?'（当前已回退）':''}`:'自动选择';text('sourceStatus',current?`${mode} · 当前：${current.label||current.id} · ${current.state||'状态未知'} · ${current.verified?'身份已验证':'身份未验证'}${current.capabilities?.reason?' · '+current.capabilities.reason:''}`:`${mode} · 当前没有可用的已验证来源`);
  }
  function validSources(x){return x&&x.schema==='lora.sources.v1'&&['auto','manual'].includes(x.selection)&&Array.isArray(x.sources)&&Number.isSafeInteger(x.selection_epoch)&&x.selection_epoch>=0;}
  async function readSources(base){const response=await fetch(base+'/api/v1/lora/sources',{cache:'no-store',signal:AbortSignal.timeout(6000)});if(!response.ok)throw Error('来源列表 HTTP '+response.status);const value=await response.json();if(!validSources(value))throw Error('来源列表格式不匹配');return value;}
  $('receiverSource').onchange=async()=>{if(sourceBusy)return;const requested=$('receiverSource').value||null,token=++sourceRequest;sourceBusy=true;$('receiverSource').disabled=true;text('sourceStatus','正在切换接收来源');loraVersion++;
    try{const base=$('gateway').value.trim().replace(/\/$/,'');const response=await fetch(base+'/api/v1/lora/sources/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_id:requested}),signal:AbortSignal.timeout(6000)});const value=await response.json();if(!response.ok)throw Error(value.error||('HTTP '+response.status));if(!validSources(value))throw Error('来源响应格式不匹配');if(token!==sourceRequest)return;sourceId=value.selected_source_id;sourceEpoch=value.selection_epoch;if($('layoutMode').value==='manual'){view=null;autoFit=true;zoom=1;}loraData=null;loraError='';loraReadAt=0;selectedEdge='';gatewaySeen=false;gatewayInterrupted=false;gatewayRecovery='正在连接接收来源';sourceBusy=false;showSources(value);render();await refreshLoRa();}
    catch(e){if(token===sourceRequest){if(sourceState)showSources(sourceState);text('sourceStatus','来源切换未完成：'+e.message+'；不会自动重试切换');}}finally{if(token===sourceRequest){sourceBusy=false;$('receiverSource').disabled=false;}}
  };
  async function refreshLoRa(){
    if(replayFrames||!isLoRa()||window.MobileStudio?.status?.mode==='demo')return;
    const token=++loraVersion,base=$('gateway').value.trim().replace(/\/$/,'');loraLoading=true;
    try{const before=await readSources(base);if(token!==loraVersion||sourceBusy)return;const response=await fetch(base+'/api/v1/lora/topology',{cache:'no-store',signal:AbortSignal.timeout(6000)});if(!response.ok)throw Error('LoRa HTTP '+response.status);const data=await response.json();const after=await readSources(base);if(token!==loraVersion||sourceBusy)return;if(before.selected_source_id!==after.selected_source_id||before.selection_epoch!==after.selection_epoch||data.source_id!==after.selected_source_id||data.selection_epoch!==after.selection_epoch){sourceId=after.selected_source_id;sourceEpoch=after.selection_epoch;if($('layoutMode').value==='manual'){view=null;autoFit=true;zoom=1;}loraData=null;loraReadAt=0;selectedEdge='';gatewaySeen=false;gatewayInterrupted=false;showSources(after);throw Error('来源读取期间发生切换，等待下一次读取');}if(sourceId!==after.selected_source_id||sourceEpoch!==after.selection_epoch){sourceId=after.selected_source_id;sourceEpoch=after.selection_epoch;if($('layoutMode').value==='manual'){view=null;autoFit=true;zoom=1;}loraData=null;loraReadAt=0;selectedEdge='';gatewaySeen=false;gatewayInterrupted=false;}showSources(after);if(data.schema!=='lora.topology.v1'||typeof data.source!=='string'||!data.source.trim()||!Array.isArray(data.reports))throw Error('LoRa 来源响应格式不匹配');if(token!==loraVersion)return;if(data.receiver?.gateway_observed===false&&!data.reports.length&&loraData?.reports?.length){const elapsed=Math.max(0,now()-loraReadAt);data.reports=loraData.reports.map(x=>({...x,pc_receive_age_ms:Number.isFinite(x.pc_receive_age_ms)?x.pc_receive_age_ms+elapsed:null}));if(!data.receiver.gateway_id)data.receiver.gateway_id=loraData.receiver?.gateway_id;}loraData=data;loraReadAt=now();loraError='';const observed=data.receiver?.gateway_observed;if(observed===true){gatewayRecovery=gatewaySeen&&gatewayInterrupted?'网关连接已恢复':'网关已连接';gatewaySeen=true;gatewayInterrupted=false;}else if(observed===false){gatewayInterrupted||=gatewaySeen;gatewayRecovery=gatewaySeen?'正在恢复网关连接':'正在连接网关';}else gatewayRecovery='网关连接状态未提供，继续读取';}
    catch(e){if(token!==loraVersion)return;loraError=e.message;gatewayInterrupted||=gatewaySeen;gatewayRecovery=gatewaySeen?'正在恢复网关连接':'正在连接网关';}finally{if(token===loraVersion){loraLoading=false;if(isLoRa())render();}}
  }
  function renderLoRaEdge(edge,detailOpen){
    const i=edge.loraReport,p=i.report,r=edge.raw,detail=$('edgeDetail');
    const params=`${lora().receiver?.mode==='node_serial'?'接收节点配置':'网关逐帧元数据'} · 上行数据率 ${i.lora?.datarate??'未提供'} · 扩频因子 ${Number.isInteger(i.lora?.sf)?'SF'+i.lora.sf:'未提供'} · 带宽 ${Number.isFinite(i.lora?.bandwidth_hz)?i.lora.bandwidth_hz/1000+' kHz':'未提供'} · 编码率 ${i.lora?.coding_rate??'未提供'} · RF 接收链 ${i.lora?.rf_chain??'未提供'}`;
    if(edge.kind==='lora_uplink'){detail.append(html('p',params));detail.append(html('strong',`${label(edge.from)} → ${label(edge.to)} · LoRa 上行`),html('p',`接收 RSSI ${Number.isFinite(i.lora?.rssi_dbm)?i.lora.rssi_dbm+' dBm':'未提供'} · SNR ${Number.isFinite(i.lora?.snr_db)?i.lora.snr_db+' dB':'未提供'} · 信道 ${i.lora?.channel??'未提供'} · 频率 ${i.lora?.frequency_hz??'未提供'} Hz · 收报年龄 ${age(i.age)}`));if(replayFrames){const seen=new Set(),values=[];for(const f of replayFrames.slice(0,Math.max(0,replayDisplayed-replayOffset)+1)){if(f.topology?.source_id!==loraData?.source_id||f.topology?.selection_epoch!==loraData?.selection_epoch)continue;for(const item of f.topology?.reports||[]){const r=item.report,key=r?.observer_boot+'/'+r?.report_seq;if(r?.observer_id===i.id&&!seen.has(key)&&Number.isFinite(item.lora?.rssi_dbm)){seen.add(key);values.push(item.lora.rssi_dbm);}}}detail.append(html('small',values.length?'本页去重 RSSI 趋势（dBm）：'+values.slice(-20).join(' → '):'本页无可用 RSSI 趋势'));}return;}
    detail.append(html('strong',`${label(edge.from)} → ${label(edge.to)} · ${sampleState(edge.state)}`));
    detail.append(html('p',`Wi-Fi 发送方 ${edge.from}\nWi-Fi 接收报告者 ${edge.to}\nWi-Fi 信道：${r.wifi_channel??'未提供'}\nWi-Fi RSSI：${edge.rssi===null?'未提供':edge.rssi+' dBm'}\n源板采样时最近听到：${age(r.seen_age_ms)}${r.seen_age_ms>=12000?'（裁顶下界）':''}\n源板采样时 ACK 年龄：${age(r.ack_age_ms)}${r.ack_age_ms>=9000?'（裁顶下界）':''}\n源板采样时 RF 帧年龄：${age(r.rf_age_ms)}${r.rf_age_ms>=12000?'（裁顶下界）':''}\n源板本地采样钟：${p.snapshot_at_ms??'未提供'} ms\n报告 boot ${p.observer_boot??'未提供'} / seq ${p.report_seq??'未提供'}；对端 boot ${r.peer_boot??'未提供'}\n上报周期 ${age(p.report_period_ms)} · 本板发前延迟 ${age(p.tx_delay_ms)}`));
    detail.append(html('p',params));
    detail.append(html('p',`LoRa 回传 ${label(i.id)} → ${label(i.gateway_id)}\nLoRa 信道：${i.lora?.channel??'未提供'} · 频率：${i.lora?.frequency_hz??'未提供'} Hz\nLoRa 接收 RSSI：${Number.isFinite(i.lora?.rssi_dbm)?i.lora.rssi_dbm+' dBm':'未提供'} / SNR：${Number.isFinite(i.lora?.snr_db)?i.lora.snr_db+' dB':'未提供'}\n网关 boot ${i.gateway_boot??'未提供'} / rx seq ${i.rx_seq??'未提供'}\n网关本地接收钟：${i.received_at_ms??'未提供'} ms\nPC 收报：${i.pc_received_at??'未提供'} · 距今 ${age(i.age)}\n读取会话：${i.reader_session??'未提供'}\n邻居表 ${p.neighbors.length}/${p.total_rows??'未提供'} · ${p.truncated?'已截断':'未截断'}${p.nd_table_full?' · ND 表曾满':''}`));
    if(replayFrames){const seen=new Set(),values=[];for(const f of replayFrames.slice(0,Math.max(0,replayDisplayed-replayOffset)+1)){if(f.topology?.source_id!==loraData?.source_id||f.topology?.selection_epoch!==loraData?.selection_epoch)continue;for(const item of f.topology?.reports||[]){const report=item.report,key=report?.observer_boot+'/'+report?.report_seq,row=report?.neighbors?.find(x=>x.peer_id===edge.from);const bits=Number.isInteger(row?.valid)?row.valid:Number.isInteger(row?.valid_flags)?row.valid_flags:null,rssi=row?.rssi_dbm??row?.wifi_rssi_dbm;if(report?.observer_id===edge.to&&!seen.has(key)&&(bits===null||(bits&2)!==0)&&Number.isFinite(rssi)){seen.add(key);values.push(rssi);}}}detail.append(html('p',values.length?'Wi-Fi RSSI 趋势（本页去重样本，dBm）：'+values.slice(-20).join(' → '):'本页无可用 Wi-Fi RSSI 趋势'));}
    detail.append(html('small','这是源板采样当时的状态；不以 LoRa 到达时间续期 Wi-Fi 9 秒互证。源板与网关本地钟不跨机相减。位置、业务收发仍来自原 Wi-Fi 观测。'));
    const raw=document.createElement('details');raw.open=detailOpen;raw.append(html('summary','原始 LoRa 收报与邻居行'),html('pre',JSON.stringify({report:i,neighbor:r},null,2)));detail.append(raw);
  }
  function renderLoRaNodes(){
    const data=lora(),nodes=graphNodes();text('statNodesLabel',isLoRa()?'节点总数':'报告节点');text('statNodes',nodes.length);text('statLocated',nodes.filter(n=>M.positionState(n,now()).valid).length);text('statOffline',nodes.filter(n=>['stale_report','interrupted','gateway_offline'].includes(data.nodes.get(n.id)?.status)).length);
    $('nodeList').replaceChildren();$('unlocated').replaceChildren();
    for(const n of nodes){const node=data.nodes.get(n.id),r=node?.report,pos=M.positionState(n,now()),status=node?.status||(r?'reported':'seen'),gw=status==='gateway'||status==='gateway_offline',b=html('button','','nodeRow state-'+status+(selected===n.id?' selected':''));b.style.setProperty('--node-state',gw?'#1f6f78':status==='reported'?'#8056ad':status==='lost'?'#b3261e':'#aa7021');b.append(html('b',label(n.id)),html('span',gw?(status==='gateway_offline'?'网关观测中断':'网关'):status==='reported'?'LoRa 在线':status==='lost'?'采样已失效':status==='stale_report'?'超时未见':status==='interrupted'?'观测中断':status==='never'?'从未观测':status==='seen_history'?'仅历史邻居观测':status==='report_unknown'?'报告状态未知':'仅被邻居看到','pill'+(gw?' gw':status==='reported'?'':status==='lost'?' off':' warn')),html('small',gw?(data.receiver?.mode==='node_serial'?'接收节点 · 仍参与 ESP-NOW':'网关接收端'):n.id),html('small',gw?'LoRa 上行接收端，逐帧上报 RSSI/SNR':r?`LoRa 报告 #${r.report.report_seq} · 最后收到 ${r.pc_received_at||'时间未提供'} · 距今 ${age(r.age)}`:status==='never'?'尚无上报或邻居观测':'仅出现在 LoRa 邻居快照中'),html('small',gw?(data.receiver?.mode==='node_serial'?'本接收入口不提供本板邻居快照':'网关不提供自身 Wi-Fi 邻居快照'):`位置另取原来源：${pos.valid?source(n.position?.source):pos.reason}`));const quality=r?.uplink_quality;b.append(html('small',quality?`上行样本 ${quality.samples??'未提供'} · 序号覆盖率 ${Number.isFinite(quality.observed_fraction)?(quality.observed_fraction*100).toFixed(1)+'%':'未提供'}`:'上行质量未提供'));b.dataset.id=n.id;b.onclick=()=>choose(n.id);$('nodeList').append(b);if(!pos.valid&&!gw)$('unlocated').append(html('div',label(n.id)+' · '+pos.reason));}
    if(!nodes.length)text('nodeList','尚无实际 LoRa 成员报告');if(!$('unlocated').children.length)text('unlocated',nodes.length?'成员沿用已有定位来源':'暂无 LoRa 成员');
    if(selected&&data.nodes.has(selected)){const r=data.nodes.get(selected).report,n=graphNodes().find(x=>x.id===selected);text('detailTitle',label(selected)+' · LoRa 观测');text('detail',r?`报告者 ${selected}\nboot ${r.report.observer_boot} / report seq ${r.report.report_seq}\n源板采样钟 ${r.report.snapshot_at_ms} ms\nPC 收报 ${r.pc_received_at||'未提供'}\nPC 收报距今 ${age(r.age)}\n位置：${n?source(n.position?.source):'无原位置来源，使用非地理拓扑'}\n邻居快照 ${r.report.neighbors.length}/${r.report.total_rows}${r.report.truncated?'，已截断':''}`:`${selected}\n该成员仅见于其他报告者的邻居行，未收到它自己的 LoRa 报告。\n位置：${n?source(n.position?.source):'无原位置来源，使用非地理拓扑'}`);}
    if(selected&&data.nodes.has(selected)){const report=data.nodes.get(selected).report?.report,box=$('detail');if(report){const status=report.status,gps=report.gps;const q=data.nodes.get(selected).report?.uplink_quality;box.append(html('p',q?`最近上行报告 · 样本 ${q.samples??'未提供'} · 序号跨度 ${q.sequence_span??'未提供'} · 序号覆盖率 ${Number.isFinite(q.observed_fraction)?(q.observed_fraction*100).toFixed(1)+'%':'未提供'} · 最近间隔 ${age(q.last_interval_ms)} · 最大间隔 ${age(q.max_interval_ms)}`:'上行质量未提供'));const item=data.nodes.get(selected).report,reason=status?.reset_reason,reasonName=({1:'上电',3:'软件复位',4:'异常复位',5:'中断看门狗',6:'任务看门狗',7:'看门狗',8:'深睡眠唤醒',9:'欠压'}[reason]||(reason?'代码 '+reason:'未采集'));box.append(html('p',status?`重启原因：${reasonName} · 可用堆：${status.heap_free_kb?status.heap_free_kb+' KiB':'未采集'} · 状态样本年龄：${age(item.status_age_ms??report.status_age_ms)}；其他状态字段尚未采集`:'节点状态块未提供'));
      box.append(html('p',status?`节点状态块原值（有效性未验证） · 节点 SF ${status.lora_sf?'SF'+status.lora_sf:'未采集'} · 节点发射功率 ${status.lora_tx_power_dbm?status.lora_tx_power_dbm+' dBm':'未采集'} · 状态块年龄 ${age(item.status_age_ms??report.status_age_ms)}`:'节点 LoRa 参数：状态块未提供'));box.append(html('p',!gps?'GPS 块未提供':gps.valid===true?`GPS 定位有效 · 纬度 ${gps.lat_e7/1e7}° · 经度 ${gps.lon_e7/1e7}° · 样本年龄 ${age(item.gps_age_ms??report.gps_age_ms)}`:`GPS 块存在，定位无效 · 样本年龄 ${age(item.gps_age_ms??report.gps_age_ms)}`));if(status||gps){const raw=document.createElement('details');raw.append(html('summary','原始状态 / GPS（调试）'),html('pre',JSON.stringify({status,gps},null,2)));box.append(raw);}}}
  }
  function reset(){sourceViews.clear();shownSource=$('topologySource').value;loraVersion++;loraData=null;loraError='';loraLoading=false;clearTimeout(radioExpiry);radioExpiry=null;model=M.create();origin=null;view=null;zoom=1;autoFit=true;logical=new Map();layoutKey='';cursor=0;selected='';selectedPacket='';selectedEdge='';packetLog=S.createPacketLog();timelineTruncated=false;animated.clear();pendingAnimation=[];snapshotLoaded=false;snapshotError='';}
  function renderHealth(){
    const studio=window.MobileStudio;
    health=S.fieldHealth({studio:studio?.status,controller:studio?.controller,upstream:studio?.upstream,nodeCount:model.nodes.size,edgeCount:M.edges(model,now()).filter(e=>e.hasObservation!==false).length,snapshotLoaded,snapshotError,external:!!$('gateway').value.trim()});
    text('fieldHealthTitle',(isLoRa()?'Wi-Fi / 业务来源：':'')+health.title);text('fieldHealthNext',health.next);$('fieldHealth').dataset.state=health.state;$('fieldHealth').classList.toggle('warning',health.warning);
    document.querySelector('.workspace').classList.toggle('staleSnapshot',!isLoRa()&&health.warning&&snapshotLoaded);
    if(!model.nodes.size)text('emptyMap',health.title);
  }
  function choose(id){if($('layoutMode').value==='clear'&&selected!==id){view=null;autoFit=true;zoom=1;}selected=id;render();}
  const edgeAge=e=>Number.isFinite(e.age)?age(e.age):Number.isFinite(e.ageUpperBound)?(Number.isFinite(e.ageLowerBound)?'≥ '+age(e.ageLowerBound)+'，':'')+'≤ '+age(e.ageUpperBound)+'（上界）':Number.isFinite(e.ageLowerBound)?'≥ '+age(e.ageLowerBound)+'（仅下界）':'未知';
  const edgeKey=e=>e.from+'/'+e.to;
  function chooseEdge(e){selectedEdge=edgeKey(e);selected=e.to;render();}
  function bounds(points){if(!points.length)return{x:-300,y:-200,w:600,h:400};const xs=points.map(p=>p.x),ys=points.map(p=>p.y),w=Math.max(160,Math.max(...xs)-Math.min(...xs)),h=Math.max(120,Math.max(...ys)-Math.min(...ys)),pad=$('layoutMode').value==='clear'?1.15:1.5;return{x:(Math.max(...xs)+Math.min(...xs))/2-w*pad/2,y:(Math.max(...ys)+Math.min(...ys))/2-h*pad/2,w:w*pad,h:h*pad};}
  function layoutNamespace(){return replayFrames?JSON.stringify(['replay',replayId,loraData?.source_id??null]):JSON.stringify([$('gateway').value.trim(),isLoRa()?'lora':'wifi',isLoRa()?sourceId:null]);}
  function ensureManual(){
    const key=layoutNamespace();if(key===manualKey)return;manualKey=key;manualPositions=new Map();
    try{const obj=JSON.parse(localStorage.getItem('mobile.manual.'+key)||'{}');for(const [id,p]of Object.entries(obj))if(typeof id==='string'&&p&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&Math.abs(p.x)<1e6&&Math.abs(p.y)<1e6)manualPositions.set(id,{x:p.x,y:p.y});}catch(_){}
  }
  function saveManual(){try{localStorage.setItem('mobile.manual.'+manualKey,JSON.stringify(Object.fromEntries(manualPositions)));}catch(_){}}
  function geometry(edges){
    const nodes=graphNodes(),located=nodes.filter(n=>M.positionState(n,now()).valid),choice=$('layoutMode').value,next=choice!=='gps';
    if(next!==topology){topology=next;view=null;zoom=1;autoFit=true;}
    const world=new Map();
    if(topology){
      const ids=[...new Set([...nodes.map(n=>n.id),...edges.flatMap(e=>[e.from,e.to])])],pairs=[...new Set(edges.map(e=>[e.from,e.to].sort().join('/')))].sort();
      const key=layoutNamespace()+'|'+ids.slice().sort().join(',')+'|'+pairs.join(',')+'|'+(choice==='clear'?selected:'');
      if(key!==layoutKey){logical=S.topology(ids,edges,choice==='clear'?selected:'');layoutKey=key;}
      if(choice==='manual'){
        ensureManual();for(const [id,p]of logical)if(!manualPositions.has(id)){let q={...p},i=0;while([...manualPositions.values()].some(v=>Math.hypot(v.x-q.x,v.y-q.y)<70)&&i<128){i++;q={x:p.x+(i%8)*85,y:p.y-Math.floor((i+7)/8)*85};}manualPositions.set(id,q);}for(const id of ids)if(manualPositions.has(id))world.set(id,manualPositions.get(id));
      }else for(const [id,p]of logical)world.set(id,p);
    }else{
      if(!origin&&located.length)origin={lat:located.reduce((s,n)=>s+n.position.lat,0)/located.length,lon:located.reduce((s,n)=>s+n.position.lon,0)/located.length};
      if(origin)for(const n of located)world.set(n.id,M.project(n.position,origin));
    }
    if(!view||autoFit&&!topology)view=bounds([...world.values()]);else if(autoFit&&topology&&[...world.values()].some(p=>p.x<view.x||p.x>view.x+view.w||p.y<view.y||p.y>view.y+view.h))view=bounds([...world.values()]);if(choice==='manual'&&world.size)autoFit=false;const s=Math.min(850/view.w,450/view.h)*zoom,cx=view.x+view.w/2,cy=view.y+view.h/2;
    const screen=p=>({x:480+(p.x-cx)*s,y:280-(p.y-cy)*s});positions=new Map([...world].map(([id,p])=>[id,screen(p)]));
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
    const layer=$('packetLayer');layer.replaceChildren();if(replayFrames)return;const row=packetRows.find(p=>p.key===selectedPacket);if(!row)return;
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
    const pairs=isLoRa()?L.pairs(edges):S.edgePairs(edges),dense=pairs.length>30,visible=($('edgeMode').value==='all'||!dense?pairs:selected?pairs.filter(p=>p.a===selected||p.b===selected):[]).filter(p=>positions.has(p.a)&&positions.has(p.b));
    const routes=[],sameEndpoints=new Map(),avoid=visible.length<=80,separate=visible.length<=24;for(const pair of visible){const a=positions.get(pair.a),b=positions.get(pair.b);if(!a||!b)continue;const obstacles=avoid?[...positions].filter(([id])=>id!==pair.a&&id!==pair.b).map(([,p])=>p):[],key=pair.a+'/'+pair.b;const previous=separate?routes:(sameEndpoints.get(key)||[]),radius=positions.size>20?18:29,shape=S.pairGeometry(a,b,obstacles,previous,radius);if(separate)routes.push(shape.samples);else sameEndpoints.set(key,[...previous,shape.samples]);
      const adjacent=!selected||selected===pair.a||selected===pair.b,chosen=pair.directions.some(e=>selectedEdge===edgeKey(e));
      const attrs={...shape.attrs,stroke:pair.color,'stroke-width':chosen?4:adjacent?3:1.8,'stroke-dasharray':pair.dash,'marker-start':pair.ba?'url(#rfArrow)':'none','marker-end':pair.ab?'url(#rfArrow)':'none',opacity:adjacent?pair.state==='stale'?.55:1:.16,class:'mapLink',tabindex:0,role:'button','data-pair':pair.key,'data-directions':pair.directions.map(edgeKey).join(','),'data-pair-state':pair.state,'aria-label':`${label(pair.a)} ${pair.both?'↔':pair.ab?'→':'←'} ${label(pair.b)} · ${pair.label}`};
      const el=svg(shape.tag,attrs),hit=svg(shape.tag,{...shape.attrs,stroke:'transparent','stroke-width':10,'pointer-events':'stroke',class:'mapLinkHit','data-hit-pair':pair.key}),title=pair.directions.map(e=>`${label(e.from)} → ${label(e.to)} · ${edgeAge(e)} · RSSI ${e.rssi===null?'未提供':e.rssi+' dBm'}`).join('\n');el.append(svg('title',{},pair.label+'\n'+title));el.onclick=hit.onclick=()=>chooseEdge(pair.ab||pair.ba);el.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();chooseEdge(pair.ab||pair.ba);}};$('linkLayer').append(hit,el);
      if(chosen){const name=pair.both?`${label(pair.a)}↔${label(pair.b)}`:pair.ab?`${label(pair.a)}→${label(pair.b)}`:`${label(pair.b)}→${label(pair.a)}`;$('linkLayer').append(svg('text',{x:shape.label.x,y:shape.label.y-3,'text-anchor':'middle','font-size':chosen?12:10,fill:pair.color,class:'edgeAgeLabel'},name+' · '+pair.label));}
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
    return {pairs,visible};
  }
  function renderMap(edges){
    const g=geometry(edges),current=now();for(const id of ['gridLayer','linkLayer','nodeLayer','scaleLayer'])$(id).replaceChildren();
    drawTiles(g);const step=[10,20,50,100,200,500,1000,5000,10000].find(v=>v*g.s>=70)||50000;
    if(!topology){const min=g.world({x:0,y:580}),max=g.world({x:960,y:0});for(let x=Math.ceil(min.x/step)*step;x<=max.x;x+=step){const p=g.screen({x,y:0});$('gridLayer').append(svg('line',{x1:p.x,y1:0,x2:p.x,y2:580,stroke:'#cbdcdb','stroke-width':.7}));}for(let y=Math.ceil(min.y/step)*step;y<=max.y;y+=step){const p=g.screen({x:0,y});$('gridLayer').append(svg('line',{x1:0,y1:p.y,x2:960,y2:p.y,stroke:'#cbdcdb','stroke-width':.7}));}}
    const {pairs,visible}=renderRadio(edges);
    for(const [id,p]of positions){const nodeRadius=positions.size>20?15:25,n=isLoRa()?graphNodes().find(x=>x.id===id):model.nodes.get(id),lr=isLoRa()?lora().nodes.get(id):null,active=isLoRa()?lr?.status==='reported':n&&M.online(n,current),group=svg('g',{class:'mapNode',tabindex:0,role:'button','data-node':id,'aria-label':`${label(id)} · ${isLoRa()?lr?.report?'LoRa 来源报告':'LoRa 快照邻居':n?active?'报告在线':'报告失联':'仅邻居观测'} · ${topology?'非地理拓扑位置':source(n?.position?.source)}`});
      const nodeState=isLoRa()?(lr?.status||(lr?.report?'reported':'seen')):null;
      // The receiver is drawn as its own vertex: teal ring, square-ish emphasis below.
      const ringColor=isLoRa()?(nodeState==='gateway'?'#1f6f78':nodeState==='reported'?'#8056ad':['lost','stale_report','interrupted','gateway_offline'].includes(nodeState)?'#b3261e':'#919b9e'):(active?'#1c8270':'#b3261e');
      group.append(svg('circle',{cx:p.x,cy:p.y,r:nodeRadius,fill:active?'#fff':nodeState==='gateway'?'#e7f4f4':['lost','stale_report','interrupted','gateway_offline'].includes(nodeState)?'#fdeceb':'#e6ebea',stroke:selected===id?'#153e46':ringColor,'stroke-width':selected===id?4:['stale_report','interrupted','gateway_offline'].includes(nodeState)?3:nodeState==='gateway'?3:2}),svg('text',{x:p.x,y:p.y+5,'text-anchor':'middle','font-size':label(id).length>5?11:positions.size>20?14:17,'font-weight':700,fill:active?'#1a655b':'#7c8b90'},label(id)));
      if(positions.size<=12||selected===id||isLoRa()&&['lost','stale_report','interrupted','gateway_offline'].includes(nodeState)||!isLoRa()&&n&&!active)group.append(svg('text',{x:p.x,y:p.y+43,'text-anchor':'middle','font-size':11,fill:['stale_report','interrupted','gateway_offline'].includes(nodeState)?'#b3261e':'#536e74','font-weight':['stale_report','interrupted','gateway_offline'].includes(nodeState)?'700':'400'},isLoRa()?lr?.report?({reported:'在线',stale_report:'超时未见',interrupted:'观测中断',report_unknown:'状态未知'}[lr.status]||'历史报告')+' · '+age(lr.report.age):lr?.status==='never'?'从未观测':lr?.status==='gateway'?(lora().receiver?.mode==='node_serial'?'节点接收端':'网关'):lr?.status==='gateway_offline'?'网关中断':lr?.status==='seen_history'?'历史邻居观测':'仅邻居快照':n?topology?M.online(n,current)?'报告在线':'报告失联':source(n.position?.source)+' · '+age(M.positionState(n,current).age):'仅邻居被观测'));
      const recent=replayFrames?null:[...model.events].reverse().find(e=>M.clean(e.reporter)===id&&['tx_submit','rx_relay','rx_local'].includes(e.event)&&Number.isFinite(e.received_ms)&&Math.max(0,(model.server?.now_ms??e.received_ms)-e.received_ms)<12000);if(recent)group.append(svg('text',{x:p.x,y:p.y-37,'text-anchor':'middle','font-size':12,'font-weight':700,fill:recent.event==='rx_local'?colors.green:colors.blue},({tx_submit:'TX 提交',rx_relay:'RELAY 收',rx_local:'RX 收到'})[recent.event]));
      const agent=n?.agent;if(active&&agent?.running===true)group.append(svg('circle',{cx:p.x+19,cy:p.y-18,r:5,fill:'#20a985'}));
      if(!replayFrames&&window.MobileStudio?.status?.mode==='live'&&window.MobileStudio?.pc?.entries?.some(e=>M.clean(e.node_id)===id&&e.connected===true))group.append(svg('text',{x:p.x,y:p.y+59,'text-anchor':'middle','font-size':10,fill:'#326eac'},'热点 IP 入口'));
      group.onclick=()=>{if(!suppressClick)choose(id);};group.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(id);}};$('nodeLayer').append(group);
    }
    $('emptyMap').classList.toggle('hidden',positions.size>0);text('emptyMap',isLoRa()&&!positions.size?loraError?'LoRa 来源不可读取':'等待实际 LoRa 邻居报告':!model.nodes.size?health?.title||'等待节点报告':topology?'尚无节点报告 · 等待接入':'无有效 GPS · 未定位节点可在列表查看');
    text('mapScope',(isLoRa()?'LoRa 回传快照 · ':'Wi-Fi 即时观测 · ')+(topology?$('layoutMode').value==='manual'?'手动布局 · 拖动节点；非地理位置':'清晰布局 · 按连接分簇；非地理位置':`GPS 等米制投影 · ${positions.size} 个有效定位 / ${graphNodes().length-positions.size} 个未定位（见列表）`)+` · ${edges.length} 个实际方向 / ${pairs.length} 对连接 · 当前显示 ${visible.length} 对${visible.length<pairs.length?'（隐藏不代表不存在）':''} · 点击节点查看一跳邻居`);
    if(!topology&&origin){const metres=[1,5,10,20,50,100,200,500,1000,5000,10000].filter(v=>v*g.s<=150).at(-1)||1,len=metres*g.s;$('scaleLayer').append(svg('path',{d:`M 36 537 V 545 H ${36+len} V 537`,stroke:'#284c50','stroke-width':2,fill:'none'}),svg('text',{x:36,y:563,'font-size':11,fill:'#284c50'},metres+' m'));}
    drawPacket();
  }
  function renderAgents(nodes){
    const pc=window.MobileStudio?.pc,entries=pc?.entries||[],demo=window.MobileStudio?.status?.mode==='demo';
    text('entrySummary',demo?'软件演示隔离运行；无实板热点或 RF 测量':pc?`PC ${pc.pc_address||pc.pc_id||'身份未提供'} · 当前有效 IP 入口 ${entries.filter(e=>e.connected===true).map(e=>label(e.node_id)).join('、')||'无'}。热点连接不等于板间 RF 邻居。`:'热点入口状态尚未读取；不推测连接状态');
    $('agents').replaceChildren();for(const n of nodes){const a=n.agent||{},card=html('article','','agentCard'),counts=a.counters||n.counts||{};
      card.append(html('strong',label(n.id)),html('span',typeof a.running==='boolean'?a.running?'运行中':'已停止':'未报告运行状态','agentState'+(a.running===true?' running':'')));
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
      if(p)$('edgeDetail').append(html('p',`即时邻居快照：匹配本次查询和双方启动身份\n观察者 boot：${p.observer_boot??'未提供'}\n样本所带对端 boot：${p.peer_boot??'未提供'}\n最近听到年龄界限：${Number.isFinite(p.seen_age_upper_bound_ms)?'≤ '+age(p.seen_age_upper_bound_ms):Number.isFinite(p.seen_age_lower_bound_ms)?'≥ '+age(p.seen_age_lower_bound_ms):'未知'} / 限制 ${age(p.seen_limit_ms??12000)}\n双向确认年龄界限：${Number.isFinite(p.confirmation_age_upper_bound_ms)?'≤ '+age(p.confirmation_age_upper_bound_ms):Number.isFinite(p.confirmation_age_lower_bound_ms)?'≥ '+age(p.confirmation_age_lower_bound_ms):'未知'} / 限制 ${age(p.confirmation_limit_ms??9000)}\n本向有效：${p.valid?'是':'否'}；本向确认：${p.confirmed?'是':'否'}；启动身份校验：${p.epoch_verified?'通过':'未通过'}\n查询 RTT 上界：${age(p.rtt_upper_bound_ms)}\n即时查询收报：${Number.isFinite(p.received_ms)?new Date(p.received_ms).toLocaleTimeString('zh-CN'):'未提供'}`));
      else $('edgeDetail').append(html('p',`观察者 boot：${edge.raw.observer_boot??'未提供'}\n样本所带对端 boot：${edge.raw.peer_boot??'未提供'}\n样本报告序号：${edge.raw.sample_report_seq??'未提供'}\n样本报告锚点：${Number.isFinite(edge.raw.sample_received_ms)?new Date(edge.raw.sample_received_ms).toLocaleTimeString('zh-CN'):'未提供'}`));
      const rssiAge=Number.isFinite(edge.rssiAge)?age(edge.rssiAge):Number.isFinite(edge.rssiUpperBound)?(Number.isFinite(edge.rssiLowerBound)?'≥ '+age(edge.rssiLowerBound)+'，':'')+'≤ '+age(edge.rssiUpperBound)+'（上界）':Number.isFinite(edge.rssiLowerBound)?'≥ '+age(edge.rssiLowerBound)+'（仅下界）':'未知';
      $('edgeDetail').append(html('p',`接收 RSSI：${edge.rssi===null?'':edge.rssi+' dBm'}\nRSSI 来源：${source(edge.rf_source)}\nRSSI 独立样本年龄：${rssiAge}\nRSSI 旧样本失效原因：${edge.raw.invalidated_reason??'无明示'}`));
      if(p){$('edgeDetail').append(html('small','连接时效来自即时查询；RSSI 采用它自己的 RF 帧年龄，不借连接确认刷新。'));if(Number.isFinite(edge.mutualRemaining))$('edgeDetail').append(html('p','本次互证剩余有效期：'+age(edge.mutualRemaining)));if(p.nd_full>0)$('edgeDetail').append(html('p','ND 表累计容量拒绝 '+p.nd_full+'；邻居观测受表容量限制。'));}
      if(edge.rssi===null)$('edgeDetail').append(html('small','原报告没有提供 RSSI，数值留空。'));
      const reverse=edges.find(e=>e.from===edge.to&&e.to===edge.from);if(reverse)$('edgeDetail').append(html('p',`反向独立样本 ${label(reverse.from)} → ${label(reverse.to)}：${radioInfo(reverse).label}；连接年龄 ${edgeAge(reverse)}；RSSI ${reverse.rssi===null?'':reverse.rssi+' dBm'}。失效方向不与仍有效方向共用箭头。`));
      const raw=document.createElement('details');raw.open=detailOpen;raw.append(html('summary','原始方向记录'),html('pre',JSON.stringify(edge.raw,null,2)));$('edgeDetail').append(raw);
    }else text('edgeDetail',selectedEdge?'该方向未列在当前快照，不能据此补造关系；请选择现有样本。':'点击图上的箭头或表格方向，查看实际 RSSI、年龄、观察者和互证依据。');
  }
  function applyNodeFilter(){
    const query=$('nodeSearch').value.trim().toLowerCase(),filter=$('nodeFilter').value,rows=[...$('nodeList').querySelectorAll('.nodeRow')];let shown=0;
    for(const row of rows){const id=row.dataset.id||'',value=(row.textContent+' '+id+' '+(model.nodes.get(id)?.label||'')+' '+(lora().labels.get(id)||'')).toLowerCase(),problem=row.classList.contains('state-lost')||row.classList.contains('state-stale_report')||row.classList.contains('state-interrupted')||row.classList.contains('state-gateway_offline')||row.classList.contains('state-never')||!!row.querySelector('.pill.off'),online=row.classList.contains('state-reported')||(!row.className.includes('state-')&&!problem);const show=(!query||value.includes(query))&&(filter==='all'||filter==='problem'&&problem||filter==='online'&&online);row.hidden=!show;if(show)shown++;}
    text('nodeCount',`显示 ${shown} / ${rows.length} · 仅筛选列表，图中节点不隐藏`);
  }
  function render(){
    if(replayFrames)text('sourceStatus','历史来源：'+(loraData?.source_id??'未提供'));$('fieldHealth').classList.toggle('hidden',!!replayFrames);document.querySelector('.businessPanel').classList.toggle('hidden',!!replayFrames);document.querySelector('.businessPanel').closest('.auxiliary').classList.toggle('hidden',!!replayFrames);$('timeline').closest('section').classList.toggle('hidden',!!replayFrames);$('timeline').closest('.auxiliary').classList.toggle('hidden',!!replayFrames);$('topologySource').disabled=!!replayFrames;$('receiverSource').disabled=!!replayFrames;$('gateway').disabled=!!replayFrames;renderHealth();renderLoRa();
    const nodes=[...model.nodes.values()],current=now(),edges=radioEdges();text('statNodesLabel',isLoRa()?'节点总数':'报告节点');text('statNodes',nodes.length);text('statLocated',nodes.filter(n=>M.positionState(n,current).valid).length);text('statLinks',edges.length);text('statOffline',nodes.filter(n=>!M.online(n,current)).length);
    $('nodeList').replaceChildren();$('unlocated').replaceChildren();for(const n of nodes){const active=M.online(n,current),pos=M.positionState(n,current),b=html('button','',`nodeRow${selected===n.id?' selected':''}`);b.append(html('b',label(n.id)),html('span',active?'报告在线':'报告失联','pill'+(active?'':' off')),html('small',n.id),html('small',`GPS ${source(n.position?.source)} · ${pos.valid?age(pos.age):pos.reason} · 报告 ${age(M.reportAge(n,current))}`));b.dataset.id=n.id;b.onclick=()=>choose(n.id);$('nodeList').append(b);if(!pos.valid)$('unlocated').append(html('div',`${label(n.id)} · ${pos.reason}`));}
    if(!nodes.length)text('nodeList','尚无实际节点报告');if(!$('unlocated').children.length)text('unlocated',nodes.length?'全部已定位':'暂无节点');
    const n=model.nodes.get(selected);text('detailTitle',n?(label(n.id))+' · 来源与状态':'选择节点查看来源');text('detail',n?`${n.id}\nboot ${n.boot_id} · 报告实例 ${n.session_id}\nGPS ${source(n.position?.source)} · ${M.positionState(n,current).reason||age(M.positionState(n,current).age)}\n${n.position?'经纬度 '+n.position.lat+', '+n.position.lon+'\n':''}报告年龄 ${age(M.reportAge(n,current))}\n节点来源 ${n.source||'网关节点报告'}\n无线来源 ${[...new Set(edges.filter(e=>e.to===n.id).map(e=>source(e.rf_source)))].join('、')||'尚无邻居样本'}`:'节点、定位、agent 和无线链路各自保留来源；不从热点客户端关系生成 RF 边');
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
    applyNodeFilter();
    text('sampleAgeTitle',isLoRa()?'源板采样时听到年龄':'连接证据年龄');
    if(!replayFrames){renderAgents(nodes);renderPackets();renderTimeline();}renderMap(edges);
  }
  async function refresh(){
    if(replayFrames)return;const token=++version;try{
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
  async function tick(){if(!observing||document.hidden||inFlight)return;inFlight=true;try{await window.MobileStudio?.ready;if(observing&&!document.hidden)await Promise.all([refresh(),refreshLoRa(),...(Date.now()>=nextFleetRead?(nextFleetRead=Date.now()+10000,[fetchFleet()]):[])]);}finally{inFlight=false;}if(observing&&!document.hidden)timer=setTimeout(tick,2000);}
  function pause(){clearInterval(agingTimer);agingTimer=null;observing=false;version++;loraVersion++;clearTimeout(radioExpiry);radioExpiry=null;clearTimeout(timer);timer=null;$('live').classList.remove('on');text('live','继续现场观测');text('connection','已暂停，保留上次观测');$('map').pauseAnimations?.();}
  function start(){observing=true;if(!agingTimer)agingTimer=setInterval(()=>{if(observing&&!document.hidden&&isLoRa())render();},1000);renderRadio(radioEdges());$('live').classList.add('on');text('live','暂停现场观测');$('map').unpauseAnimations?.();tick();}
  async function replayRequest(path,options){
    const response=await fetch(path,options);
    if(!response.ok)throw Error('HTTP '+response.status);
    return response.json();
  }
  async function listReplay(){
    try{
      const value=await replayRequest('/api/v1/replay/sessions');
      const select=$('replaySessions'),old=select.value;
      select.replaceChildren(new Option('选择实验',''));
      for(const item of value.sessions||[])
        select.add(new Option(new Date(item.started_ms).toLocaleString('zh-CN')+(item.active?' · 记录中':''),item.id));
      select.value=old;
      text('replayStatus',value.error?'记录异常中止：'+value.error:value.active_id?'正在记录 LoRa 观测':'实时观测；回放时间为电脑观察时间');
    }catch(e){text('replayStatus','记录服务不可用：'+e.message);}
  }
  async function replayShow(previous=null){
    const i=Number($('replayTime').value),ticket=++replayRequestSeq,id=replayId;
    if(!id)return;
    try{
      if(!replayFrames||i<replayOffset||i>=replayOffset+replayFrames.length){
        const offset=Math.floor(i/30)*30;
        const value=await replayRequest('/api/v1/replay/session?id='+encodeURIComponent(id)+'&offset='+offset+'&limit=30');
        if(ticket!==replayRequestSeq||id!==replayId)return;
        if(!Array.isArray(value.frames)||!Number.isSafeInteger(value.total)||value.total<0||value.offset!==offset||value.frames.length>30)
          throw Error('回放分页接口格式不匹配');
        replayFrames=value.frames;replayOffset=offset;replayTotal=value.total;
        $('replayTime').max=String(Math.max(0,value.total-1));
      }
      const frame=replayFrames[i-replayOffset];
      if(!frame)throw Error('该时刻没有快照');
      if(Number.isFinite(previous)&&Number.isFinite(frame.t_ms))
        await new Promise(resolve=>{replayTimer=setTimeout(resolve,Math.max(0,Math.min(2147483647,frame.t_ms-previous)));});
      if(ticket!==replayRequestSeq||id!==replayId)return;
      replayDisplayed=i;replayTimestamp=frame.t_ms;loraData=frame.topology;loraReadAt=now();loraError='';loraCache=null;gatewayRecovery='历史快照';
      text('replayStatus','历史观测 · 第 '+(i+1)+' / '+replayTotal+' 帧 · '+new Date(frame.t_ms).toLocaleString('zh-CN')+' · 空快照不代表断链');
      render();return frame;
    }catch(e){
      if(ticket===replayRequestSeq){replayPlaying=false;text('replayPlay','播放');text('replayStatus','回放读取失败：'+e.message);}
    }
  }
  async function replayStep(){
    if(!replayPlaying)return;
    const i=Number($('replayTime').value);
    if(i>=replayTotal-1){replayPlaying=false;text('replayPlay','播放');return;}
    const previous=replayFrames?.[i-replayOffset]?.t_ms;
    $('replayTime').value=String(i+1);
    const frame=await replayShow(previous);
    if(!frame||!replayPlaying)return;
    replayTimer=setTimeout(replayStep,0);
  }
  $('recordStart').onclick=async()=>{try{await replayRequest('/api/v1/replay/start',{method:'POST'});await listReplay();}catch(e){text('replayStatus','开始失败：'+e.message);}};
  $('recordStop').onclick=async()=>{try{await replayRequest('/api/v1/replay/stop',{method:'POST'});await listReplay();}catch(e){text('replayStatus','结束失败：'+e.message);}};
  $('replayOpen').onclick=async()=>{
    try{
      const id=$('replaySessions').value;
      if(!id)throw Error('请先选择实验');
      const value=await replayRequest('/api/v1/replay/session?id='+encodeURIComponent(id)+'&offset=0&limit=30');
      if(!Array.isArray(value.frames)||!Number.isSafeInteger(value.total)||value.offset!==0||value.frames.length>30||!value.total)
        throw Error('分页接口不可用或实验没有快照');
      clearTimeout(replayTimer);replayPlaying=false;version++;loraVersion++;
      replayId=id;replayFrames=value.frames;replayOffset=0;replayTotal=value.total;
      $('topologySource').value='lora';$('replayTime').max=String(value.total-1);$('replayTime').value='0';
      await replayShow();
    }catch(e){text('replayStatus','打开失败：'+e.message);}
  };
  $('replayTime').oninput=()=>{
    replayPlaying=false;clearTimeout(replayTimer);text('replayPlay','播放');replayShow();
  };
  $('replayPlay').onclick=()=>{
    if(!replayId)return;
    replayPlaying=!replayPlaying;clearTimeout(replayTimer);
    if(!replayPlaying){replayRequestSeq++;$('replayTime').value=String(replayDisplayed);}
    text('replayPlay',replayPlaying?'暂停':'播放');
    if(replayPlaying)replayStep();
  };
  $('replayEvents').onchange=()=>{if(!$('replayEvents').value)return;$('replayTime').value=$('replayEvents').value;replayPlaying=false;clearTimeout(replayTimer);text('replayPlay','播放');replayShow();};
  $('replayIndex').onclick=async()=>{
    const id=replayId,select=$('replayEvents');
    if(!id){text('replayStatus','请先打开实验');return;}
    select.replaceChildren(new Option('选择事件',''));
    let last=null,previousObservation=null,count=0;
    try{
      for(let offset=0;offset<replayTotal;offset+=30){
        const x=await replayRequest('/api/v1/replay/session?id='+encodeURIComponent(id)+'&offset='+offset+'&limit=30');
        if(id!==replayId)return;
        if(!Array.isArray(x.frames)||x.offset!==offset||x.frames.length>30||!x.frames.length)throw Error('事件索引分页异常');
        for(let j=0;j<x.frames.length;j++){
          const f=x.frames[j],t=f.topology||{},receiver=t.receiver||{};
          const valid=receiver.gateway_observed===true&&typeof t.source_id==='string';
          const key=JSON.stringify([t.source_id,t.selection_epoch,receiver.gateway_id]);
          const add=msg=>{
            if(count>=10000)return;
            const display=msg.replace(/(?:[0-9a-f]{2}:){5}[0-9a-f]{2}/ig,mac=>label(mac));
            select.add(new Option(new Date(f.t_ms).toLocaleTimeString('zh-CN')+' · '+display,String(offset+j)));
            count++;
          };
          if(previousObservation&&previousObservation.valid!==valid)
            add((valid?'网关观测恢复':'网关观测中断')+(previousObservation.key!==key?'（来源身份变化或未提供）':''));
          previousObservation={key,valid};
          if(!valid){last=null;continue;}
          const snapshot=L.snapshot(t,0,[],false),nodes=new Map(),edges=new Map();
          for(const n of snapshot.nodes.values())if(n.report)nodes.set(n.id+'/'+n.report.report.observer_boot,n.status);
          for(const pair of L.pairs(snapshot.edges.filter(e=>e.kind!=='lora_uplink')))
            if(pair.state!=='historical')edges.set(pair.key+'/'+pair.directions.map(e=>e.from+'>'+e.to).sort().join('|'),pair.state);
          for(const edge of snapshot.edges)
            if(edge.kind!=='lora_uplink'&&!edge.historical)edges.set('方向 '+edge.from+' → '+edge.to,edge.state);
          if(last&&last.key===key){
            for(const [node,state]of nodes)
              if(last.nodes.has(node)&&last.nodes.get(node)!==state&&['reported','stale_report'].includes(state)&&['reported','stale_report'].includes(last.nodes.get(node)))
                add(node+' · '+(state==='reported'?'报告恢复':'超时未见'));
            for(const [edge,state]of edges)
              if(last.edges.has(edge)&&last.edges.get(edge)!==state)add(edge+' · '+last.edges.get(edge)+' → '+state);
          }
          last={key,nodes,edges};
        }
        text('replayStatus',`索引 ${Math.min(offset+x.frames.length,replayTotal)} / ${replayTotal} · ${count} 项（中断及缺行不判断链）`);
        await new Promise(resolve=>setTimeout(resolve,0));
      }
      text('replayStatus',`事件索引完成 · ${count} 项（上限10000；中断及缺行不判断链）`);
    }catch(e){text('replayStatus','事件索引失败：'+e.message);}
  };
  $('replayLive').onclick=()=>{
    clearTimeout(replayTimer);replayTimer=null;replayPlaying=false;replayRequestSeq++;
    version++;loraVersion++;replayId=null;replayFrames=null;loraData=null;loraCache=null;loraError='';sourceEpoch=null;
    gatewayRecovery='正在连接接收来源';text('sourceStatus','等待新的实时来源');text('replayPlay','播放');
    text('replayStatus','正在恢复实时观测');text('connection','实时 · 等待新数据');
    if(!observing)start();else{clearTimeout(timer);timer=null;if(!inFlight)tick();}
    render();refreshLoRa();
  };
  listReplay();
  $('refresh').onclick=()=>{if(!inFlight)Promise.all([refresh(),refreshLoRa()]);};$('live').onclick=()=>observing?pause():start();
  $('topologySource').onchange=()=>{if(window.MobileStudio?.status?.mode==='demo')$('topologySource').value='wifi';try{localStorage.setItem('mobile.topology.source',$('topologySource').value);}catch(_){}
    sourceViews.set(shownSource,{origin,view,zoom,autoFit,logical,layoutKey,selectedEdge,selected,topology});shownSource=$('topologySource').value;const saved=sourceViews.get(shownSource);
    origin=saved?.origin||null;view=saved?.view||null;zoom=saved?.zoom||1;autoFit=saved?.autoFit??true;logical=saved?.logical||new Map();layoutKey=saved?.layoutKey||'';selectedEdge=saved?.selectedEdge||'';selected=saved?.selected||'';topology=saved?.topology??true;if($('layoutMode').value==='manual'){view=null;autoFit=true;zoom=1;}
    loraVersion++;render();if(observing&&!document.hidden)refreshLoRa();};
  $('edgeMode').onchange=render;$('nodeSearch').oninput=applyNodeFilter;$('nodeFilter').onchange=applyNodeFilter;$('clearNodeFilter').onclick=()=>{$('nodeSearch').value='';$('nodeFilter').value='all';applyNodeFilter();};
  $('layoutMode').onchange=()=>{try{localStorage.setItem('mobile.layout.mode',$('layoutMode').value);}catch(_){}view=null;autoFit=true;zoom=1;layoutKey='';render();};$('resetLayout').onclick=()=>{if($('layoutMode').value==='manual'){ensureManual();manualPositions.clear();saveManual();}layoutKey='';view=null;autoFit=true;zoom=1;render();};$('fit').onclick=()=>{autoFit=true;view=null;zoom=1;render();};$('zoomIn').onclick=()=>{autoFit=false;zoom=Math.min(8,zoom*1.4);render();};$('zoomOut').onclick=()=>{autoFit=false;zoom=Math.max(.25,zoom/1.4);render();};$('tiles').onchange=render;$('eventFilter').onchange=renderTimeline;$('packetStateFilter').onchange=renderPackets;$('packetOverlay').onchange=()=>drawPacket();
  $('replayPacket').onclick=()=>{const p=packetRows.find(p=>p.key===selectedPacket);if(p){pendingAnimation=p.events;drawPacket(true);}};
  $('gateway').onchange=()=>{loraVersion++;loraData=null;loraError='';version++;clearTimeout(timer);timer=null;if(observing)tick();};
  document.addEventListener('studiohealth',renderHealth);
  // Toggling the GPS layer must redraw at once instead of waiting for the next poll.
  document.addEventListener('studiogps',()=>{version++;loraVersion++;if(!observing||document.hidden)return;Promise.all([refresh(),refreshLoRa()]).catch(()=>{});});
  document.addEventListener('studiochanging',()=>{if(replayFrames)return;version++;clearTimeout(timer);timer=null;reset();instance=null;text('sourceBadge','正在切换，等待同一来源报告');render();});
  document.addEventListener('studiochange',()=>{if(replayFrames)return;const demo=window.MobileStudio?.status?.mode==='demo',loraOption=$('topologySource').querySelector('option[value="lora"]');if(demo)$('topologySource').value='wifi';if(loraOption)loraOption.disabled=demo;version++;reset();instance=null;clearTimeout(timer);timer=null;render();if(observing&&!document.hidden){if(inFlight)setTimeout(()=>{if(observing&&!document.hidden)tick();},100);else tick();}});
  let drag=null;const svgPoint=e=>{const pt=$('map').createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;return pt.matrixTransform($('map').getScreenCTM().inverse());};
  $('map').addEventListener('pointerdown',e=>{
    const node=e.target.closest('.mapNode');if(e.target.closest('.mapLink,.mapLinkHit'))return;const g=geometry(radioEdges()),start=g.world(svgPoint(e));
    if(node){if($('layoutMode').value!=='manual')return;ensureManual();const id=node.dataset.node,p=manualPositions.get(id);if(!p)return;drag={kind:'node',id,start,p:{...p},g,x:e.clientX,y:e.clientY,moved:false};}
    else drag={kind:'pan',start,view:{...view},g,x:e.clientX,y:e.clientY,moved:false};
    $('map').setPointerCapture(e.pointerId);
  });
  $('map').addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(!drag.moved&&Math.hypot(dx,dy)<4)return;drag.moved=true;autoFit=false;const nowWorld=drag.g.world(svgPoint(e));if(drag.kind==='node')manualPositions.set(drag.id,{x:drag.p.x+nowWorld.x-drag.start.x,y:drag.p.y+nowWorld.y-drag.start.y});else view={...drag.view,x:drag.view.x-(nowWorld.x-drag.start.x),y:drag.view.y-(nowWorld.y-drag.start.y)};render();});
  function finishDrag(){if(!drag)return;const done=drag;drag=null;if(done.moved){suppressClick=true;if(done.kind==='node')saveManual();setTimeout(()=>suppressClick=false,0);}else if(done.kind==='node')choose(done.id);}
  $('map').addEventListener('pointerup',finishDrag);$('map').addEventListener('pointercancel',finishDrag);
  document.addEventListener('visibilitychange',()=>{version++;loraVersion++;clearTimeout(timer);timer=null;if(document.hidden){clearInterval(agingTimer);agingTimer=null;clearTimeout(radioExpiry);radioExpiry=null;$('map').pauseAnimations?.();text('connection','页面隐藏，读取已暂停');}else if(observing){if(!agingTimer)agingTimer=setInterval(()=>{if(observing&&!document.hidden&&isLoRa())render();},1000);renderRadio(radioEdges());$('map').unpauseAnimations?.();tick();}});window.addEventListener('pagehide',pause);
  function syncContext(){
    text('contextMode',replayFrames?'历史回放':observing?'实时观测':'观测已暂停');
    text('contextTime',replayFrames&&Number.isFinite(replayTimestamp)?(matchMedia('(max-width:600px)').matches?new Date(replayTimestamp).toLocaleTimeString('zh-CN'):'第 '+(replayDisplayed+1)+' / '+replayTotal+' 帧 · '+new Date(replayTimestamp).toLocaleString('zh-CN')):$('connection').textContent);
    document.querySelector('.liveTools').classList.toggle('hidden',!!replayFrames);
    $('contextMode').dataset.mode=replayFrames?'history':observing?'live':'paused';
  }
  new MutationObserver(syncContext).observe($('replayStatus'),{childList:true,subtree:true,characterData:true});
  new MutationObserver(syncContext).observe($('connection'),{childList:true,subtree:true,characterData:true});
  render();start();syncContext();
})();

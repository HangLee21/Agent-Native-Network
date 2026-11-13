'use strict';
// Route presentation never owns a send plan or submits a run.
window.routeView = (() => {
  let epoch=0,debounce=null,playTimer=null,syncing=false,view='draft';
  let shown=null,candidate=null,simPacket=null,simJob=null,hardware=null,hardwarePackets=[],hardwareReadVersion=0,liveEpoch=null;
  const mode=()=>document.body.dataset.operation;
  const key=()=>JSON.stringify([mode(),draft,$('algorithm').value,$('nodeSet').value,$('previewPhase').value,edgeMode]);
  const rows=()=>records.filter(p=>p.arm===$('resultArm').value);
  const simTime=()=>($('previewPhase').value==='window'?(draft.fault_start_s+draft.fault_end_s)/2:$('previewPhase').value==='recovered'?draft.fault_end_s:0);
  const nodeLabel=(n,bindings)=>nodes.includes(n)?n:Object.keys(bindings||{}).find(k=>String(bindings[k]).toLowerCase()===String(n).toLowerCase());
  const pathEdges=p=>p.slice(1).map((n,i)=>[p[i],n]);
  function stop(){clearInterval(playTimer);playTimer=null;text('replayPlay','播放保存包');}
  function setView(v){view=v;$('routeView').value=v;}
  function clear(note){if(window.joinReplay?.active())return window.joinReplay.paint();shown=null;actual=[];text('graphPath',note);text('routeRaw','');$('graph').setAttribute('aria-label','可编辑五板网络；'+note);paint();}
  function display(value){shown=value;if(window.joinReplay?.active())return window.joinReplay.paint();actual=[];text('graphPath',value.note);text('routeRaw',json(value.evidence));paint();}
  function options(){for(const o of $('routeView').options)o.hidden=o.value!=='draft'&&o.value!==(mode()==='hardware'?'hardware':'simulation');}
  function changed(reason='draft'){
    const was=view;epoch++;readJobVersion++;clearTimeout(debounce);stop();setView('draft');options();candidate=null;
    if(window.joinReplay?.active()){window.joinReplay.paint();return;}
    if(mode()==='adhoc'){clear('AD-HOC入口不计算路线；请打开本机单板工作台。');return;}
    clear('草稿规划更新中…');
    if(mode()==='simulation'){
      const arm=$('algorithm').value;
      const hasArm=[...$('resultArm').options].some(o=>o.value===arm);
      if(hasArm){
        syncing=true;$('resultArm').value=arm;chooseArm();syncing=false;
      }else{$('resultArm').selectedIndex=-1;$('packet').replaceChildren();simPacket=null;updateReplay();}
      // An algorithm switch while inspecting a saved run also switches that run's arm.
      if(reason==='algorithm'&&was==='simulation'){setView('simulation');if(hasArm)showSimulation();else{simPacket=null;updateReplay();clear('当前保存运行没有所选算法的逐包结果，不沿用其他策略路径。');}}
    }
    debounce=setTimeout(()=>requestPreview(epoch,key()),300);
  }
  async function requestPreview(version,requestKey){
    if(!draft||!window.senderCapabilitiesReady||mode()==='adhoc')return;
    const saved=clone(draft),hardwareMode=mode()==='hardware',algorithm=$('algorithm').value;
    const current=()=>version===epoch&&requestKey===key();
    function unavailable(note){if(!current())return;candidate=null;if(view==='draft')clear(note);text(hardwareMode?'hardwarePlanText':'candidates',note);}
    if(!validate())return unavailable('无法规划：请先修正上方设置。');
    if(edgeMode)return unavailable('分机状态以本板记录为准；本页没有集中沿途观测，不绘制推测的完整路径。');
    if(hardwareMode&&saved.hops===null&&algorithm!=='mid')return unavailable('实板规划：请选择恰好1–4跳，或原MID不限跳。');
    if(hardwareMode&&algorithm!=='mid'&&saved.hops>=$('nodeSet').value.length)return unavailable('当前参与节点不足以组成'+saved.hops+'跳路线（'+saved.hops+'跳需要'+(saved.hops+1)+'个节点）。旧高亮已清除。');
    if(!hardwareMode&&algorithm==='mid')return unavailable('原MID / SOCP不使用时延枚举候选；查看保存的MID结果，或显式运行受支持的A↔B不限跳配置。');
    const body=hardwareMode?{settings:saved,mode:algorithm==='mid'?'mid':'hops',count:1,node_set:[...$('nodeSet').value]}:{settings:saved,time_s:simTime()};
    try{
      const r=await api(hardwareMode?'/api/hardware/plan':'/api/plan',body);
      if(!current())return;
      const p=hardwareMode?(r.plan||r):(r.preview||r),paths=hardwareMode?(p.chain?.length?[p.chain]:[]):(p.candidates||[]).map(c=>c.path);
      const bindings=p.bindings||snapshot?.labels||{},path=(paths[0]||[]).map(n=>nodeLabel(n,bindings));
      if(path.length<2||path.some(n=>!n)||path[0]!==saved.src||path.at(-1)!==saved.dst||(saved.hops!==null&&path.length-1!==saved.hops))return unavailable('没有满足当前源、目的及恰好跳数的候选路线。旧高亮已清除。');
      const note=hardwareMode?'草稿规划（未发包）：'+path.join(' → ')+' · '+(path.length-1)+'跳\n原假设模型；参与节点 '+body.node_set.join('、')+'。'+(p.run_available?'':(' 当前不可发送：'+(p.availability?.reasons||[]).join('；'))):'草稿候选（未运行）：'+path.join(' → ')+' · '+(path.length-1)+'跳 · 模型时刻 '+body.time_s+'秒\n'+(algorithm==='fixed'?'固定策略从开始时选路；此处只是所选时刻可达候选，历史实际请看保存包。':'当前时刻枚举候选；运行中的观测、计算和配置到达有延迟，实际请看保存包。');
      candidate={kind:'planned',path,edges:pathEdges(path),complete:true,note,evidence:{kind:'planned_only',version,request:body,response:p}};
      text(hardwareMode?'hardwarePlanText':'candidates',note+(paths.length>1?'\n其他候选：'+paths.slice(1).map(p=>p.join(' → ')).join('；'):''));
      // Deliberately discard plan_id: the payload sender obtains its own bound plan.
      if(view==='draft')display(candidate);
    }catch(e){unavailable('路线预览失败：'+e.message+'。旧高亮已清除。');}
  }
  function previewNow(){epoch++;clearTimeout(debounce);stop();candidate=null;setView('draft');clear('草稿规划更新中…');return requestPreview(epoch,key());}
  function updateReplay(){const list=rows(),index=Number($('packet').value)||0;$('replayPosition').max=String(Math.max(0,list.length-1));$('replayPosition').value=String(index);$('replayPosition').disabled=!list.length;$('replayPlay').disabled=list.length<2;text('replayTime',simPacket?`${index+1} / ${list.length} · 生成 ${simPacket.generated_s}秒 · ${simPacket.received_s==null?'未收到':'收到 '+simPacket.received_s+'秒'}`:'没有可回放的逐包记录');}
  function simulationPacket(p,j){simPacket=p;simJob=j;updateReplay();if(mode()==='simulation'&&!syncing){setView('simulation');showSimulation();}}
  function showSimulation(){
    if(mode()!=='simulation')return;
    if(!simPacket||!simJob)return clear('此保存运行没有实际逐包路径；不使用候选补齐。');
    const p=simPacket,path=Array.isArray(p.actual_path)?p.actual_path.filter(n=>nodes.includes(n)):[];
    const complete=p.delivered===true&&p.received_s!=null&&path.at(-1)===p.dst;
    display({kind:'actual',path,edges:pathEdges(path),complete,note:'保存仿真实际包 '+p.packet_id+' · '+(labels[p.arm]||p.arm)+'\n'+(path.join(' → ')||'无接收链')+' · '+(complete?'目的已收':'未确认目的接收，仅显示已记录段')+' · 生成 '+p.generated_s+'秒\n来源 '+simJob.run_id+'；按该运行冻结配置，不随当前草稿重算。',evidence:{kind:'saved_simulation_packet',run_id:simJob.run_id,frozen_settings:simJob.settings,packet:p}});
    updateReplay();
  }
  function loadingSimulation(){stop();simPacket=null;simJob=null;updateReplay();if(mode()==='simulation'){setView('simulation');clear('读取保存的仿真包…');}}
  function failed(note){epoch++;clearTimeout(debounce);candidate=null;stop();clear(note);}
  function hardwareRecord(j,live=false){
    hardware=j;hardwarePackets=j.packets||j.result?.packets||j.result?.summary?.packets||[];
    $('savedHardwareRun').value=j.run_id||'';
    $('hardwarePacket').replaceChildren(...hardwarePackets.map((p,i)=>new Option('包 '+(i+1)+' · '+(p.destination_received?'目的已收':'目的未确认'),String(i))));
    if(mode()==='hardware'&&(!live||liveEpoch===epoch)){setView('hardware');showHardware();}
  }
  function showHardware(){
    if(!hardware||!hardwarePackets.length)return clear('保存实板记录没有逐包证据；不以规划路线补齐。');
    const p=hardwarePackets[Number($('hardwarePacket').value)||0],id=Array.isArray(p.identity)?p.identity:[p.origin??p.identity?.origin,p.origin_boot??p.identity?.origin_boot,p.seq??p.identity?.seq,p.dst??p.identity?.dst];
    const bindings=hardware.plan_snapshot?.bindings||hardware.result?.bindings||snapshot?.labels||{};
    if(id.length!==4||id.some(x=>x==null))return clear('实板包身份不完整，不能关联沿途记录。');
    const origin=nodeLabel(id[0],bindings),dst=nodeLabel(id[3],bindings),edges=(p.actual_edges||[]).map(e=>[nodeLabel(e.node,bindings),nodeLabel(e.next_hop,bindings)]).filter(e=>e.every(Boolean));
    const relays=(p.relays||[]).map(n=>nodeLabel(n,bindings)).filter(Boolean),path=origin?[origin]:[];
    // Follow only uniquely logged outgoing segments; never append the plan's chain.
    while(path.length<=nodes.length){const next=[...new Set(edges.filter(e=>e[0]===path.at(-1)).map(e=>e[1]))];if(next.length!==1||path.includes(next[0]))break;path.push(next[0]);}
    const complete=!!origin&&!!dst&&p.destination_received===true&&path.at(-1)===dst&&path.slice(1,-1).every(n=>relays.includes(n));
    const note='保存实板实际记录：'+(complete?path.join(' → '):(edges.map(e=>e.join(' → ')).join('；')||'无沿途段'))+'\n'+(p.destination_received?'目的 rx_local 已匹配原包及载荷':'目的接收未确认')+'；中继 RX '+(relays.join('、')||'无记录')+'。箭头来自 tx_submit，缺失段不补齐。\n运行 '+hardware.run_id+' · 身份 '+id.join(' / ');
    text('hardwareEvidence',note);
    display({kind:'actual',path:complete?path:[],edges,complete,note,evidence:{kind:'saved_hardware_packet',run_id:hardware.run_id,identity:id,bindings,packet:p,source_directory:hardware.output_directory||hardware.result?.output_directory,complete_chain:complete}});
  }
  async function loadHardware(){
    const id=$('savedHardwareRun').value.trim(),version=++hardwareReadVersion;epoch++;readJobVersion++;stop();hardware=null;hardwarePackets=[];$('hardwarePacket').replaceChildren();setView('hardware');clear('读取保存的实板记录…');text('hardwareEvidence','');
    if(!/^[0-9a-f]{24}$/.test(id)){clear('实板运行ID应为24位小写十六进制。旧高亮已清除。');return;}
    const graphEpoch=epoch;
    try{const r=await api('/api/hardware/runs/'+id);if(version!==hardwareReadVersion||graphEpoch!==epoch||view!=='hardware'||mode()!=='hardware')return;hardwareRecord(r.run||r);}catch(e){if(version===hardwareReadVersion&&graphEpoch===epoch&&view==='hardware')clear('保存实板记录读取失败：'+e.message+'。旧高亮已清除。');}
  }
  function paint(){
    if(window.joinReplay?.active())return window.joinReplay.paint();
    const edges=$('routeEdges'),rings=$('routeNodes');edges.replaceChildren();rings.replaceChildren();if(!shown)return;
    const ns='http://www.w3.org/2000/svg',color=shown.kind==='planned'?'#246eb7':'#c96b1b';
    const svg=(name,attrs,parent)=>{const el=document.createElementNS(ns,name);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,v);parent.append(el);return el;};
    shown.edges.forEach(([a,b],i)=>{if(!pos[a]||!pos[b])return;const [x,y]=pos[a],[u,v]=pos[b],len=Math.hypot(u-x,v-y),dx=(u-x)/len,dy=(v-y)/len;
      svg('line',{x1:x+dx*36,y1:y+dy*36,x2:u-dx*39,y2:v-dy*39,stroke:color,'stroke-width':6,'marker-end':'url(#routeArrow'+(shown.kind==='planned'?'Blue':'Orange')+')','data-from':a,'data-to':b,'data-kind':shown.kind},edges);
      const mx=(x+u)/2,my=(y+v)/2;svg('circle',{cx:mx,cy:my,r:13,fill:'white',stroke:color,'stroke-width':2},edges);
      svg('text',{x:mx,y:my+5,'text-anchor':'middle',fill:color,'font-size':14,'font-weight':'bold'},edges).textContent=shown.complete?String(i+1):'·';
    });
    const routeNodes=[...new Set(shown.edges.flat())];for(const n of routeNodes){const[x,y]=pos[n];svg('circle',{cx:x,cy:y,r:34,fill:'none',stroke:color,'stroke-width':4,'data-node':n},rings);const i=shown.path.indexOf(n);if(i>=0)svg('text',{x:x+36,y:y-25,fill:color,'font-size':16,'font-weight':'bold'},rings).textContent=i===0?'起点':i===shown.path.length-1?(shown.complete?'终点':'记录末端'):String(i)+' 中继';}
    $('graph').setAttribute('aria-label','可编辑五板网络；'+shown.note.replace(/\n/g,'；'));
  }
  $('routeView').onchange=()=>{stop();setView($('routeView').value);if(view==='draft'){if(candidate)display(candidate);else previewNow();}else if(view==='simulation')showSimulation();else if(hardware)showHardware();else loadHardware();};
  $('previewPhase').onchange=()=>changed();$('nodeSet').addEventListener('change',()=>changed());$('operation').addEventListener('change',()=>changed());
  $('loadHardwareRecord').onclick=loadHardware;$('hardwarePacket').onchange=()=>{setView('hardware');showHardware();};
  $('savedHardwareRun').oninput=()=>{hardwareReadVersion++;hardware=null;hardwarePackets=[];$('hardwarePacket').replaceChildren();if(view==='hardware')clear('运行ID已改，请读取保存记录。');};
  $('replayPosition').oninput=()=>{stop();$('packet').value=$('replayPosition').value;choosePacket();};
  $('replayPlay').onclick=()=>{if(playTimer){stop();return;}const list=rows();if(list.length<2)return;if(Number($('packet').value)>=list.length-1)$('packet').value='0';choosePacket();text('replayPlay','暂停回放');playTimer=setInterval(()=>{const i=Number($('packet').value)+1;if(mode()!=='simulation'||i>=rows().length){stop();return;}$('packet').value=String(i);choosePacket();},400);};
  $('packet').addEventListener('change',stop);$('resultArm').addEventListener('change',()=>{stop();const arm=$('resultArm').value;if([...$('algorithm').options].some(o=>o.value===arm&&!o.hidden)){$('algorithm').value=arm;messageEdit();changed('algorithm');}});
  $('reset').addEventListener('click',()=>{epoch++;readJobVersion++;clearTimeout(debounce);candidate=null;$('previewPhase').value='0';setView('draft');stop();clear('恢复实测基线中；旧高亮已清除。');});
  document.addEventListener('capabilitieschange',()=>changed());
  options();if(draft)changed();
  return {changed,paint,previewNow,simulationPacket,hardwareRecord,loadingSimulation,failed,sending:()=>{liveEpoch=epoch;},revision:()=>epoch};
})();

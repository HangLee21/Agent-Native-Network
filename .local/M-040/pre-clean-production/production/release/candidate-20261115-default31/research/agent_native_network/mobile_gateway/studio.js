'use strict';
// Controls only the optional same-origin studio. No board/serial/business API calls.
window.MobileStudio=(()=>{
  const $=id=>document.getElementById(id);let status=null,pc=null,available=null,busy=false,epoch=0,operationError='',readVersion=0,nextProbe=0;
  let controller={available:null,checking:true,legacy:false,error:''},upstream={state:'checking',error:''};
  const changed=()=>document.dispatchEvent(new Event('studiohealth'));
  async function api(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',cache:'no-store',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(body===undefined?6000:20000)});if(!response.ok){const error=Error('HTTP '+response.status);error.status=response.status;throw error;}return response.json();}
  function render(){
    const demo=status?.demo||{},mode=status?.mode||'live',state=demo.running?'running':demo.exit_code==null?'stopped':demo.exit_code===0?'finished':'failed';
    $('fieldMode').classList.toggle('active',mode==='live');$('demoMode').classList.toggle('active',mode==='demo');
    for(const id of ['fieldMode','demoMode','demoStart','demoStop','demoReplay'])$(id).disabled=busy||available!==true;
    $('demoStart').disabled||=mode!=='demo'||demo.running===true;
    $('demoStop').disabled||=demo.running!==true;
    $('demoReplay').disabled||=mode!=='demo';
    if(!busy)$('fakeGPS').checked=status?.fake_gps===true;$('fakeGPS').disabled=busy||available!==true;
    $('demoControls').classList.toggle('hidden',mode!=='demo');
    $('studioSource').textContent=available===false?controller.legacy?'独立观测网关 · 无演示控制器':'现场控制器暂未连接 · 保留原数据源':mode==='demo'?'软件演示 · fake_agent / fake_gps · host_model，非实板 RF':'现场观测 · 仅实际报告；GPS 与无线来源分别标示';
    const liveState=upstream.state==='unreachable'?'上游业务服务未连接':upstream.state==='connected'?status?.error?'业务服务在线 · 节点观测查询暂未成功':'上游业务服务在线':'正在连接上游业务服务';
    $('studioState').textContent=operationError||(available===false?controller.legacy?'演示控制请打开本机8794':'现场控制器暂未连接，将自动重连':available===null?'检查控制器…':mode==='live'?liveState:`演示 ${{running:'运行中',stopped:'未启动 / 已停止',finished:'已结束',failed:'失败'}[state]}${demo.running&&Number.isFinite(demo.elapsed_s)?' · '+demo.elapsed_s.toFixed(0)+' / '+demo.duration_s+' s':''}`);
    $('observationMode').textContent=mode==='demo'?'软件演示 · 过程观测':'现场网络 · 持续观测';document.body.dataset.studioMode=mode;
  }
  async function refresh(){
    if(available===false&&Date.now()<nextProbe)return;
    const token=++readVersion;if(available===null){controller={...controller,checking:true};changed();}
    try{
      const value=await api('/api/studio/status');if(token!==readVersion)return;
      status=value;available=true;controller={available:true,checking:false,legacy:false,error:''};
      if(value.mode==='live'){
        if(upstream.state==='checking')changed();
        try{const current=await api('/api/pc/status');if(token!==readVersion)return;pc=current;upstream={state:'connected',error:''};}
        catch(e){if(token!==readVersion)return;pc=null;upstream={state:'unreachable',error:e.message};}
      }else{pc=null;upstream={state:'checking',error:''};}
      render();changed();return value;
    }catch(e){
      if(token!==readVersion)return;available=false;nextProbe=Date.now()+10000;pc=null;
      controller={available:false,checking:false,legacy:e.status===404,error:e.message};render();changed();
    }
  }
  async function command(path,body={}){if(busy||available!==true)return;busy=true;operationError='';render();document.dispatchEvent(new Event('studiochanging'));try{const response=await api(path,body);epoch++;status=response.status||response;await refresh();document.dispatchEvent(new Event('studiochange'));}catch(e){operationError='操作结果未确认：'+e.message+'；请读取状态，不自动重试。';document.dispatchEvent(new Event('studiochange'));}finally{busy=false;render();}}
  $('fieldMode').onclick=()=>command('/api/studio/mode',{mode:'live'});$('demoMode').onclick=()=>command('/api/studio/mode',{mode:'demo'});
  $('demoStart').onclick=()=>command('/api/studio/demo',{action:'start'});$('demoStop').onclick=()=>command('/api/studio/demo',{action:'stop'});$('demoReplay').onclick=()=>command('/api/studio/demo',{action:'restart'});
  $('fakeGPS').onchange=()=>command('/api/studio/gps',{enabled:$('fakeGPS').checked}).then(()=>document.dispatchEvent(new Event('studiogps')));
  render();const ready=refresh();return{refresh,ready,get status(){return status;},get pc(){return pc;},get controller(){return controller;},get upstream(){return upstream;},get epoch(){return epoch;}};
})();

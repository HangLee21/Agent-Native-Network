"""Render only newly computed events, never stored example curves."""
import json,statistics

def build(folder):
    index=json.loads((folder/'INDEX.json').read_bytes());arms=[];events={};seconds={};packets={}
    settings=json.loads((folder/'settings.json').read_bytes());routing=settings.get('schema') in ['mid.routing.settings.v1','mid.measured.settings.v1'] and index.get('algorithm') not in ['mid','compare_mid']
    for item in index['runs']:
        arm=item['arm'];path=folder/item['path'];rows=[json.loads(x) for x in (path/'events.jsonl').read_bytes().splitlines()];context=json.loads((path/'context.json').read_bytes());generated={e['packet_id']:e for e in rows if e['event']=='generate'};rx={}
        for e in rows:
            if e['event']=='destination_rx':
                assert e['packet_id'] in generated and e['node']==e['dst'] and e['payload_tag']==generated[e['packet_id']]['payload_tag'];rx.setdefault(e['packet_id'],e)
        duration=context['duration_s'];series=[]
        for t in range(duration):
            series.append(dict(second=t,received=sum(t<=e['t_s']<t+1 for e in rx.values()),goodput_bps=256*sum(t<=e['t_s']<t+1 for e in rx.values())))
        packet_rows=[]
        for pid,gen in generated.items():
            hops=[dict(node=e['node'],t_s=e['t_s'],event=e['event'],source_line=line) for line,e in enumerate(rows,1) if e.get('packet_id')==pid and e['event']==('hop_rx' if routing else 'rx')]
            if not routing:hops.insert(0,dict(node=gen['src'],t_s=gen['t_s'],event='generate'))
            actual=[e['node'] for e in hops];received=rx.get(pid);drop=next((e for e in reversed(rows) if e.get('packet_id')==pid and e['event']=='drop'),None)
            if routing and received:
                assert actual==received['actual_path'] and len(set(actual))==len(actual)
                assert settings['hops'] is None or len(actual)-1==settings['hops']
            packet_rows.append(dict(packet_id=pid,src=gen['src'],dst=gen['dst'],generated_s=gen['t_s'],received_s=received['t_s'] if received else None,
                planned_path=gen.get('locked_path'),path_version=gen.get('path_version'),actual_path=actual,hop_events=hops,actual_hops=len(actual)-1 if actual else 0,
                delivered=received is not None,delivery_status='delivered' if received else 'dropped' if drop else 'pending',drop_reason=drop.get('reason') if drop else None,
                source_events=item['events']))
        packets[arm]=packet_rows
        latency=[e['t_s']-generated[k]['t_s'] for k,e in rx.items()];arms.append(dict(item,received=len(rx),packets=packet_rows,latency_mean_s=statistics.mean(latency) if latency else None,latency_median_s=statistics.median(latency) if latency else None));seconds[arm]=series
        events[arm]=[{k:v for k,v in e.items() if k not in ['observation','table']} for e in rows if e['event'] in ['generate','tx_attempt','arrival','rx','hop_rx','destination_rx','drop','config_install','config_publish','plan_start','plan_end','candidate_paths','run_cancelled']]
    labels=dict(fixed='固定初始链' if routing else '固定初表',latency_aware='时延感知改道',adaptive='MID重规划')
    result=dict(index,arms=arms,settings=settings,seconds=seconds,events=events,packets=packets,strategy_labels=labels,routing_policy='latency_aware_simple_path' if routing else 'original_MID_SOCP',scope='本次真实软件仿真；时延为同一模拟时钟之差，不是RF测量。')
    if routing:
        from settings_api import module
        preview=module(settings).preview
        result['candidates']=preview(settings,0)['candidates']
        result['candidate_windows']=[dict(time_s=t,candidates=preview(settings,t)['candidates'],scope='scenario_preview_only') for t in [0,(settings['fault_start_s']+settings['fault_end_s'])/2,settings['fault_end_s']]]
    (folder/'view.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    data=json.dumps(result,ensure_ascii=False).replace('</','<\/')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>本次链路模拟回放</title><style>body{font:18px system-ui;max-width:1100px;margin:35px auto;background:#f2f6fa;color:#193950;padding:20px}section{padding:25px;background:white;margin:20px 0;border-radius:12px}svg{width:100%}input{width:90%}pre{white-space:pre-wrap;font-size:13px;max-height:300px;overflow:auto}button,select{font:inherit;padding:10px}</style><h1>本次真实软件仿真</h1><a href="/">返回编辑控制台</a><p id="summary"></p><section><h2>目的有效吞吐（bit/s）</h2><p>蓝：固定初表　绿：MID重规划；横轴为模拟秒</p><svg id="plot" viewBox="0 0 1000 230"></svg></section><section><h2>模拟事件回放</h2><select id="arm"><option value="fixed">固定初表</option><option value="adaptive">MID重规划</option></select><button id="play">播放 / 暂停</button><p id="time"></p><input id="slider" type="range" min="0" step="0.1" value="0"><svg id="graph" viewBox="0 0 1000 330"></svg><pre id="ev"></pre></section><details><summary>本次冻结的设置</summary><pre id="settings"></pre></details><script id="data" type="application/json">DATA</script><script>
const d=JSON.parse(document.getElementById('data').textContent),$=x=>document.getElementById(x),NS='http://www.w3.org/2000/svg',pos={A:[100,160],C:[340,70],E:[340,260],D:[620,160],B:[880,160]};let playing=false;const duration=d.settings.duration_s;$('arm').replaceChildren(...d.arms.map(a=>new Option(d.strategy_labels[a.arm],a.arm)));$('slider').max=duration;$('settings').textContent=JSON.stringify(d.settings,null,2);$('summary').textContent=d.arms.map(a=>d.strategy_labels[a.arm]+'：源生成'+a.generated+'，目的收到'+a.received+'；接收包平均模拟时延'+(a.latency_mean_s==null?'未知':a.latency_mean_s.toFixed(3)+'秒')).join('；')+'。'+d.scope;
function el(tag,attrs,text){let n=document.createElementNS(NS,tag);for(let[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!=null)n.textContent=text;return n}const ymax=Math.max(512,...Object.values(d.seconds).flat().map(x=>x.goodput_bps));for(let [arm,rs] of Object.entries(d.seconds)){$('plot').append(el('polyline',{points:rs.map(e=>(50+e.second/duration*900)+','+(190-e.goodput_bps/ymax*160)).join(' '),fill:'none',stroke:arm==='fixed'?'#315fd0':'#008493','stroke-width':3}))}$('plot').append(el('text',{x:50,y:220},'0'));$('plot').append(el('text',{x:910,y:220},duration+'秒'));$('plot').append(el('text',{x:0,y:30},ymax));
function render(){let t=Number($('slider').value),arm=$('arm').value,ev=(d.events[arm]||[]).filter(e=>e.t_s<=t&&e.t_s>=t-.5);$('time').textContent=t.toFixed(1)+' 模拟秒';$('graph').replaceChildren();for(let edge of d.settings.links.filter(e=>e.connected)){let a=pos[edge.src],b=pos[edge.dst];$('graph').append(el('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:'#d5e0e8','stroke-width':2}))}for(let e of ev.filter(e=>e.event==='rx'&&e.previous_hop)){let a=pos[e.previous_hop],b=pos[e.node];if(a&&b)$('graph').append(el('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:'#008493','stroke-width':6}))}for(let [n,p] of Object.entries(pos)){$('graph').append(el('circle',{cx:p[0],cy:p[1],r:25,fill:'#193e63'}));$('graph').append(el('text',{x:p[0],y:p[1]+7,fill:'white','text-anchor':'middle'},n))}$('ev').textContent=ev.map(e=>e.t_s.toFixed(3)+' '+e.event+' '+(e.node||'')+' '+(e.packet_id||'')+' '+(e.reason||'')).join('\n')||'本时间窗没有事件';} $('slider').oninput=render;$('arm').onchange=render;$('play').onclick=()=>playing=!playing;setInterval(()=>{if(playing){$('slider').value=(Number($('slider').value)+.1)%duration;render()}},100);render();
</script></html>'''.replace('DATA</script>',data+'</script>')
    if routing:html=html.replace('蓝：固定初表　绿：MID重规划','蓝：固定初始链　绿：时延感知改道（非MID）')
    (folder/'index.html').write_text(html,encoding='utf-8');return result

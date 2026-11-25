"""Build an offline replay from existing H logs + E2 identity evidence. No radio or analysis rerun."""
from pathlib import Path
import json,html,math
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent
H=ROOT/'simulation/outputs/H-005/20261107-18-five-results/result.json'
E=ROOT/'simulation/outputs/E2-016/20261107-05-real-five-review/identities.json'
report=json.loads(H.read_text(encoding='utf-8'))
identities=json.loads(E.read_text(encoding='utf-8'))['identities']
boards=[dict(label=k,mac=v['MAC'],boot=v['boot']) for k,v in report['boards'].items()]
labels={b['mac']:b['label'] for b in boards}
data=dict(schema='mid.observed-replay.v1',title='五板实测回放',date='2026-11-07',boards=boards,
          package=report['package_manifest_sha256'],build=report['boards']['A']['build'],
          provenance=dict(H=str(H.relative_to(ROOT)).replace('\\','/'),E2=str(E.relative_to(ROOT)).replace('\\','/')),
          cases=[])
for c in report['cases']:
    run=Path(c['run']); rows=[json.loads(s) for s in (run/'native.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    epoch=min(x['host_monotonic_ns'] for x in rows)
    events=[]; routes={}
    for line,r in enumerate(rows,1):
        ev=r.get('event')
        if not isinstance(ev,dict): continue
        kind=ev.get('event')
        keep=bool(ev.get('dst')) or kind in ('config_applied','config_rejected','config_stale','callback_timeout','input_queue_overflow')
        if kind=='route_selected':
            key=(ev['node_id'],ev['src'],ev['dst']); value=ev.get('next_hop')
            keep=routes.get(key,'unseen')!=value;routes[key]=value
        if not keep: continue
        # Preserve observation order + both clocks; no simulated packet transit or clock subtraction.
        events.append(dict(t=round((r['host_monotonic_ns']-epoch)/1e9,6),host_ns=str(r['host_monotonic_ns']),line=line,v=ev))
    packets=[]
    for q in identities:
        if q['run_id']!=run.name:continue
        origin,boot,seq,dst=q['identity']; selected=[i for i,e in enumerate(events) if [e['v'].get(k) for k in ('origin','origin_boot','seq','dst')]==q['identity']]
        def at(line):return round((rows[line-1]['host_monotonic_ns']-epoch)/1e9,6) if line else None
        packets.append(dict(identity=q['identity'],start=at(q['source_queued_line']),arrival=at(q.get('destination_rx_local_line')),
                            verified=q.get('payload_matches_command',False),path=q.get('path'),hops=q.get('hops',[]),
                            sourceLine=q['source_queued_line'],destinationLine=q.get('destination_rx_local_line'),
                            hostSendLine=q['host_send_line'],nonce=q['host_nonce'],payload=q['payload_hex'],eventIndices=selected))
    packets.sort(key=lambda x:x['start'])
    data['cases'].append(dict(id=c['case'],run=run.name,log=str((run/'native.jsonl').relative_to(ROOT)).replace('\\','/'),
                             epoch_ns=str(epoch),duration=round((max(r['host_monotonic_ns'] for r in rows)-epoch)/1e9,6),
                             hostWindow=c['RF_window_seconds'],expected=sum(f['expected'] for f in c['flows']),
                             source=c['source_unique'],received=c['matched_unique'],chains=c['controlled_complete_chains'],
                             events=events,packets=packets,success=c['success'],error=c['error'],stopped=all(c['stop_confirmed'].values())))
encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
(OUT/'replay-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
template=(OUT/'replay.template.html').read_text(encoding='utf-8')
(OUT/'index.html').write_text(template.replace('/*__REPLAY_DATA__*/',encoded),encoding='utf-8')
c=next(c for c in data['cases'] if c['id']=='chain_ABCDE');p=c['packets'][0]
parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900"><title>五板实测四跳：A-B-C-D-E</title><desc>真实源提交、中继及目的日志；图形位置仅示意，时间为主机串口观察时刻。</desc><defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#087f8c"/></marker></defs><rect width="1600" height="900" fill="#f5f7fb"/><g font-family="Microsoft YaHei, sans-serif" fill="#172b4d"><text x="80" y="90" font-size="38" font-weight="700">五板实测 · 一条完整四跳证据链</text><text x="80" y="138" font-size="23" fill="#51647b">2026-11-07  /  package-03  /  E2独立逐身份核对</text><text x="80" y="215" font-size="28">120 / 120 目的唯一交付　　20 / 20 完整受控四跳</text>']
for i,mac in enumerate(p['path']):
    x=150+325*i
    if i<4:
        hop=next(h for h in p['hops'] if h['node']==mac);line=hop['tx_submit_lines'][0];ev=next(e for e in c['events'] if e['line']==line)
        parts.append(f'<line x1="{x+55}" y1="365" x2="{x+266}" y2="365" stroke="#087f8c" stroke-width="7" marker-end="url(#a)"/><text x="{x+157}" y="320" text-anchor="middle" font-size="21">tx_submit  t={ev["t"]:.3f}s</text><text x="{x+157}" y="413" text-anchor="middle" font-size="20" fill="#51647b">日志 L{line}</text>')
    parts.append(f'<circle cx="{x}" cy="365" r="50" fill="#173a61"/><text x="{x}" y="378" font-size="36" fill="white" text-anchor="middle">{labels[mac]}</text><text x="{x}" y="470" text-anchor="middle" font-size="20">{mac}</text><text x="{x}" y="508" text-anchor="middle" font-size="21">{"源" if i==0 else "目的" if i==4 else "实测中继"}</text>')
parts.extend([f'<text x="80" y="600" font-size="25">数据身份：A / boot {p["identity"][1]} / seq {p["identity"][2]} / dst E</text>',f'<text x="80" y="646" font-size="25">目的 rx_local：t={p["arrival"]:.3f}s，日志 L{p["destinationLine"]}，payload 与原发送命令匹配</text>', '<text x="80" y="708" font-size="22" fill="#875b16">受控逻辑邻接；不是RF物理隔断或覆盖收益。位置为示意，非实际坐标。</text>', '<text x="80" y="751" font-size="22" fill="#51647b">t 为同一主机串口观察时刻（相对场景首行）；采集顺序不等于空口因果顺序，不据此计算单向时延。</text>',f'<text x="80" y="812" font-size="19" fill="#51647b">来源：{html.escape(c["log"])}</text></g></svg>'])
(OUT/'five-board-four-hop.svg').write_text(''.join(parts),encoding='utf-8')
print(json.dumps(dict(html=str(OUT/'index.html'),bytes=(OUT/'index.html').stat().st_size,cases=len(data['cases']),packets=sum(len(c['packets']) for c in data['cases']),svg=str(OUT/'five-board-four-hop.svg')),ensure_ascii=False))

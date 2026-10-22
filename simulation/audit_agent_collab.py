"""Validate full sweep and produce stratified paired summaries."""
import csv
import json
import hashlib
from collections import defaultdict
from simulation.agent_collab import OUT, ROOT, POLICIES


def main():
    rows=list(csv.DictReader((OUT/'metrics.csv').open()))
    keys=('need','result_size','background','rate','intermittent')
    by={tuple(r[k] for k in keys)+(r['seed'],r['policy']):r for r in rows}
    assert len(rows)==len(by)==8640
    for r in rows:
        assert 10 <= float(r['mean_completion']) <= 210
        if r['need']=='0.0':assert float(r['mean_completion'])==10
        if r['background']=='0' and r['policy'] in ('priority','on_demand'):
            fifo=by[tuple(r[k] for k in keys)+(r['seed'],'fifo')]
            for metric in ('mean_completion','collaborative','fallback','link_bytes'):
                assert r[metric]==fifo[metric]
    meta=json.loads((OUT/'metadata.json').read_text())
    for name,digest in meta['hashes'].items():
        assert hashlib.sha256((ROOT/'simulation'/name).read_bytes()).hexdigest()==digest
    groups=defaultdict(list)
    for r in rows:groups[tuple(r[k] for k in keys)+(r['policy'],)].append(r)
    summary=[]
    for key, group in groups.items():
        assert len(group)==24
        item=dict(zip(keys+('policy',),key))
        for metric in ('mean_completion','collaborative','fallback','link_bytes','requests_received','results_received'):
            item[metric]=sum(float(r[metric]) for r in group)/24
        differences=[float(r['mean_completion'])-float(by[tuple(r[k] for k in keys)+(r['seed'],'independent')]['mean_completion']) for r in group]
        item['paired_delay_vs_local']=sum(differences)/24
        summary.append(item)
    with (OUT/'summary.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    lines=['# 辅助观测协作：首轮结果','',
        '2026-10-22。8640次、24种子、72个任务/网络条件、5策略。全部原始记录、360条种子0事件轨迹及360条条件汇总已保存。运动和链路时序在策略间固定；采用4节点链路服务模型。','',
        '## 主要发现','',
        '协作收益随必要结果大小、背景流量和接触时序变化。短结果、连续连接时，已有任务优先策略可保护协作流程；间歇连接时，请求和结果分别等待接触，等待本身会改变“请求协作还是本地完成”的选择。','',
        '以下固定需求比例1、容量1024字节/秒，列出这一容量下全部8种背景/结果/接触组合。数值是24种子的平均任务完成延迟（秒），越低越好；其余容量及需求比例完整见summary.csv。','',
        '|间歇连接|结果字节|背景字节/次|本地执行|即时网络|FIFO|任务优先|按需推送|',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for intermittent in ('False','True'):
        for size in ('512','65536'):
            for bg in ('0','65536'):
                values=[]
                for policy in POLICIES:
                    r=next(r for r in summary if tuple(r[k] for k in keys)+(r['policy'],)==('1.0',size,bg,'1024',intermittent,policy))
                    values.append(r['mean_completion'])
                lines.append('|'+('是' if intermittent=='True' else '否')+f'|{size}|{bg}|'+ '|'.join(f'{v:.2f}' for v in values)+'|')
    lines += ['',
        '## 初步模型导出的研究问题','',
        '**任务通信的代价需要进入端侧协作决策。** 观测本身5秒、最终动作10秒，但请求与结果要分别经过两跳。节点只按固定120秒等待后再本地执行，可能把90秒可完成的任务拖至210秒。因此下一阶段把“协作接纳、等待预算、本地回退”列为应用—网络接口变量，并用多种等待预算和并行本地处理作强对照。','',
        '**消息服务与任务依赖要共同评价。** 背景65536字节每30秒向两个端点推送，经两跳消耗的平均链路负载约8738字节/秒；在1024字节/秒条件下为预设过载。任务优先主要检验过载时保护必要交互的效果。必要结果本身较大时，削减背景仍有容量约束，需结合任务的内容需求选择交付方式。','',
        '## 审计与模型口径','',
        '- 无辅助需求：全部策略10秒完成。无背景：三种实用通信策略一致。',
        '- 即时网络平均17.5秒，保留两个请求共用观测服务台的排队；连续高容量网络21.5秒，增加四次逐跳交付。',
        '- 任务均有最终本地回退，因此本轮全部12项任务在预算内完成，区分度体现在完成时间和合作/回退比例。',
        '- 每个任务有独立执行槽，表示并发检查作业；物理机器人单任务占用和实际观察点移动在下一版资源模型加入。',
        '- 断连传输保留字节进度，采用可靠链路服务；记录链路应用字节。接收与服务事件保持因果次序。',
        '- 首轮采用固定120秒等待、5秒观测及90秒本地代价；它们是机制输入，后续按完整范围扫描。',
        '- 本轮规则智能体共享消息接口但不共享任务状态。端侧模型接入后，额外记录实际请求结构、计算时延与任务变化。','',
        '## 复现','',
        '`.venv/Scripts/python.exe -m simulation.agent_collab`',
        '`.venv/Scripts/python.exe -m simulation.audit_agent_collab`',
        '`.venv/Scripts/python.exe -m unittest simulation.test_agent_collab -q`','']
    (OUT/'INTERPRETATION.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Audited 8640 records; saved 360 stratified summaries and interpretation.')


if __name__=='__main__':main()
